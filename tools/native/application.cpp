// Stable Python ABI for one Mognitio application, compiled from its manifest
// by this payload's paired compiler in the dedicated run child.
#define PY_SSIZE_T_CLEAN
#define Py_LIMITED_API 0x030C0000
#include <Python.h>
#include <asmjit/x86.h>
#include <csignal>
#include <cstdint>
#include <cstring>
#include <new>
#include <vector>

namespace {
class Owned {
public:
    explicit Owned(PyObject *value) : value_(value) {}
    ~Owned() { Py_XDECREF(value_); }
    Owned(const Owned&) = delete;
    Owned& operator=(const Owned&) = delete;
    PyObject *get() const { return value_; }
private:
    PyObject *value_;
};

PyObject *fail(const char *message) {
    PyErr_SetString(PyExc_RuntimeError, message);
    return nullptr;
}

struct AppMemory {
    void *address = nullptr;
    size_t size = 0;
    ~AppMemory() { if (address) asmjit::VirtMem::release(address, size); }
};

bool prepare(PyObject *manifest, AppMemory& memory) {
    Owned service(PyImport_ImportModule("tools.selfhost.resident"));
    if (!service.get()) return false;
    Owned result(PyObject_CallMethod(service.get(), "compile_project", "O", manifest));
    if (!result.get()) return false;
    if (PyTuple_Size(result.get()) != 2) { fail("Invalid paired compiler result"); return false; }
    char *body = nullptr, *refs = nullptr;
    Py_ssize_t count = 0, refs_count = 0;
    if (PyBytes_AsStringAndSize(PyTuple_GetItem(result.get(), 0), &body, &count) ||
        PyBytes_AsStringAndSize(PyTuple_GetItem(result.get(), 1), &refs, &refs_count)) return false;
    if (count <= 0 || count > INT32_MAX || refs_count % 4) { fail("Invalid application dimensions"); return false; }

    asmjit::CodeHolder code;
    if (code.init(asmjit::Environment::host())) { fail("Cannot initialize native linker"); return false; }
    asmjit::x86::Assembler output(&code);
    size_t cursor = 0, length = static_cast<size_t>(count);
    for (Py_ssize_t i = 0; i < refs_count; i += 4) {
        uint32_t offset;
        std::memcpy(&offset, refs + i, 4);
        if (offset < cursor || offset > length || length - offset < 8) {
            fail("Invalid compiler reference position"); return false;
        }
        uint64_t reference;
        std::memcpy(&reference, body + offset, 8);
        constexpr uint64_t image_text = 4194424;
        if (reference < image_text || reference - image_text >= length) {
            fail("Invalid compiler reference target"); return false;
        }
        auto label = output.newLabel();
        if (!label.isValid() || output.embed(body + cursor, offset - cursor) ||
            code.bindLabel(label, 0, reference - image_text) || output.embedLabel(label, 8)) {
            fail("Cannot bind compiler reference"); return false;
        }
        cursor = offset + 8;
    }
    if (output.embed(body + cursor, length - cursor) || code.flatten() || code.resolveUnresolvedLinks() ||
        code.codeSize() != length) { fail("Incomplete application layout"); return false; }
    memory.size = length;
    using Flags = asmjit::VirtMem::MemoryFlags;
    if (asmjit::VirtMem::alloc(&memory.address, length, Flags::kAccessRW) ||
        code.relocateToBase(reinterpret_cast<uintptr_t>(memory.address)) ||
        code.copyFlattenedData(memory.address, length) ||
        asmjit::VirtMem::protect(memory.address, length, Flags::kAccessRX)) {
        fail("Cannot finalize native application memory"); return false;
    }
    asmjit::VirtMem::flushInstructionCache(memory.address, length);
    return true;
}

PyObject *run_project(PyObject *, PyObject *params) {
    PyObject *manifest, *args;
    if (!PyArg_ParseTuple(params, "UO!:run_project", &manifest, &PyTuple_Type, &args)) return nullptr;
    try {
        AppMemory application;
        if (!prepare(manifest, application)) return nullptr;
        Py_ssize_t count = PyTuple_Size(args);
        std::vector<uintptr_t> arguments(static_cast<size_t>(count) + 3, 0);
        arguments[0] = static_cast<uintptr_t>(count + 1);
        arguments[1] = reinterpret_cast<uintptr_t>("mgn-run");
        for (Py_ssize_t i = 0; i < count; ++i) {
            char *value;
            Py_ssize_t size;
            if (PyBytes_AsStringAndSize(PyTuple_GetItem(args,i), &value, &size)) return nullptr;
            if (std::memchr(value, 0, static_cast<size_t>(size))) return fail("Invalid application argument");
            arguments[static_cast<size_t>(i) + 2] = reinterpret_cast<uintptr_t>(value);
        }
        struct sigaction previous{}, normal{};
        normal.sa_handler = SIG_DFL;
        sigemptyset(&normal.sa_mask);
        if (sigaction(SIGINT, nullptr, &previous) || (previous.sa_handler != SIG_IGN && sigaction(SIGINT, &normal, nullptr)))
            return fail("Cannot prepare application signal state");
        using ApplicationEntry = void (*)(const uintptr_t *);
        reinterpret_cast<ApplicationEntry>(application.address)(arguments.data());
        return fail("Application returned outside its runtime");
    } catch (const std::bad_alloc&) { return PyErr_NoMemory(); }
}

PyMethodDef methods[] = {{"run_project", run_project, METH_VARARGS, "Run the verified compiler's application for a manifest."},
                         {nullptr, nullptr, 0, nullptr}};
PyModuleDef module = {PyModuleDef_HEAD_INIT, "_application", nullptr, -1, methods, nullptr, nullptr, nullptr, nullptr};
}
PyMODINIT_FUNC PyInit__application() { return PyModule_Create(&module); }
