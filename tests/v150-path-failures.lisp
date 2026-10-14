(in-package #:mognitio.tests)

(deftest v150-host-status-and-full-width-identity
  (dolist (pair '((36 "InvalidPath") (2 "NotFound") (1 "PermissionDenied") (13 "PermissionDenied")
                  (20 "UnsupportedTarget") (95 "UnsupportedTarget") (12 "ResourceExhausted")
                  (23 "ResourceExhausted") (24 "ResourceExhausted") (28 "ResourceExhausted")
                  (122 "ResourceExhausted") (40 "Other") (5 "Other")))
    (let ((mognitio.io::*path-inspection-fault-hook* (lambda () (- (first pair)))))
      (multiple-value-bind (out err code) (v12-driver (v150-manifest (v150-error "/original///" (second pair))))
        (same "" out) (same "" err) (same 0 code))))
  (dolist (status '(-9 -14 -22 -4096 1))
    (let ((mognitio.io::*path-inspection-fault-hook* (lambda () status)))
      (signals internal-failure (mognitio.io::inspect-path-value (v12-text "/")))))
  (let* ((calls 0) (mognitio.io::*path-inspection-fault-hook* (lambda () (when (= (incf calls) 1) -4))))
    (same 1 (mognitio.io::inspect-path-value (v12-text "/"))) (same 2 calls))
  (let ((mognitio.io::*path-inspection-fault-hook* (lambda () (error "Invalid input reached the OS"))))
    (dolist (path (list "" (string (code-char 0))))
      (signals mognitio.io::directory-failure (mognitio.io::inspect-path-value (v12-text path)))))
  (flet ((id (a b) (mognitio.io::%file-identity a b)))
    (dolist (word '(0 4294967296 9223372036854775808 18446744073709551615))
      (is (mognitio.io::file-identity-equal (id word word) (id word word)))
      (is (mognitio.io::file-identity-not-equal (id word 0) (id word 1)))
      (is (mognitio.io::file-identity-not-equal (id 0 word) (id 1 word))))))

(deftest v150-native-status-cleanup-and-retry
  (dolist (pair '((36 "InvalidPath") (2 "NotFound") (1 "PermissionDenied") (13 "PermissionDenied")
                  (20 "UnsupportedTarget") (95 "UnsupportedTarget") (12 "ResourceExhausted")
                  (23 "ResourceExhausted") (24 "ResourceExhausted") (28 "ResourceExhausted")
                  (122 "ResourceExhausted") (40 "Other") (5 "Other")))
    (let ((image (v12-native (v150-manifest (v150-error "/original///" (second pair)))
                  (list :inspection-stat-fault (- (first pair)) :inspection-cleanup-fault -28))))
      (multiple-value-bind (out err code trace) (v12-trace image)
        (same "" out) (same "" err) (same 0 code)
        (is (search "munmap(" trace)) (is (not (search "close(3)" trace))))))
  (let ((image (v12-native (v150-manifest (v150-error "/" "ResourceExhausted")) '(:inspection-cleanup-fault -28))))
    (multiple-value-bind (out err code) (process-result (list (namestring image)))
      (same "" out) (same "" err) (same 0 code)))
  (let ((image (v12-native (v150-manifest (v150-kind "/" "Directory")))))
    (multiple-value-bind (out err code trace) (v12-trace image "newfstatat:error=EINTR:when=1")
      (same "" out) (same "" err) (same 0 code)
      (same 2 (count-if (lambda (line) (search "newfstatat(" line)) (uiop:split-string trace :separator '(#\Newline))))))
  (dolist (status '(-9 -14 -22))
    (let ((image (v12-native (v150-manifest "discard inspectPath(\"/\");0") (list :inspection-stat-fault status))))
      (multiple-value-bind (out err code trace) (v12-trace image)
        (declare (ignore err))
        (same "" out) (same 3 code)
        (is (search "munmap(" trace))))))

(deftest v150-allocation-failures
  (dolist (kind '(:path-inspection :file-identity :data))
    (let* ((manifest (v150-manifest "discard inspectPath(\"/\");0"))
           (mognitio.runtime::*allocation-hook*
             (lambda (at) (when (eq kind at) (error 'storage-condition)))))
      (multiple-value-bind (out err code) (v12-driver manifest)
        (same "" out) (same 4 code) (is (search "allocation failure" err)))))
  ;; Result construction follows the actual scratch munmap, even under GC stress.
  (let ((manifest (v150-manifest "discard inspectPath(\"/\");0")))
    (loop for allocation from 2 to 5 do
      (multiple-value-bind (out err code trace)
          (v12-trace (v12-native manifest (list :fail-allocation allocation :stress t :validate t)))
        (same "" out) (same 4 code) (is (search "allocation failure" err))
        (let ((release (search "munmap(" trace)) (diagnostic (search "write(2," trace)))
          (is (and release diagnostic (< release diagnostic))))))))

(deftest v150-static-negative-surface
  (dolist (body '("discard inspectPath(1);0" "let x:FileIdentity=FileIdentity{};0"
                  "discard FileIdentity(1);0" "discard FileIdentity{1};0"
                  "let x:FileIdentity=1;0" "let f:Function(String):Int=inspectPath;0"
                  "let x:FileIdentity<Int>=panic{\"no\"};0"))
    (signals source-failure (project-checked (v150-manifest body))))
  (dolist (expression '("id<id" "id+id" "id==1" "id->device" "id->hash()" "id->toInt()"))
    (signals source-failure
      (project-checked (v150-manifest (format nil "let p:PathInfo=~A;let id:FileIdentity=p->identity;discard ~A;0" (v150-info "/") expression)))))
  (signals source-failure
    (project-checked (v150-manifest "0"
      "use Std\\Io\\{IoError};let wrong:Function():Result<PathInfo,IoError>=function():Result<PathInfo,IoError>{Result<PathInfo,IoError>::Ok(try inspectPath(\"/\"))};")))
  (signals source-failure (project-checked (project-fixture (list (cons "app.mgn"
    "namespace App;let main:Function(List<String>):Int=function(args:List<String>):Int{discard inspectPath(\"/\");0};")))))
  (v150-both "let e:PathInfoError=PathInfoError{kind:IoErrorKind::Other,subject:\"data\"};assert e->subject==\"data\";0"))

(deftest v150-core-proof-mutations
  (dolist (mutation '(:type :arguments :operation))
    (let* ((module (mognitio.ir:lower-program (project-checked (v150-manifest "discard inspectPath(\"/\");0"))))
           (inst (loop for fn in (mognitio.ir:module-functions module) thereis
                   (loop for block in (mognitio.ir:ir-function-blocks fn) thereis
                     (find :inspect-path (mognitio.ir:basic-block-instructions block) :key #'mognitio.ir:instruction-value)))))
      (is inst)
      (ecase mutation
        (:type (setf (mognitio.ir:instruction-type inst) :int))
        (:arguments (setf (mognitio.ir:instruction-operands inst) nil))
        (:operation (setf (mognitio.ir:instruction-value inst) :read-file)))
      (signals internal-failure (mognitio.ir:verify-module module)))))

(deftest v150-function-storage-without-observation
  (let* ((manifest (v150-manifest
           "let functions:List<Function(String):Result<PathInfo,PathInfoError>>=List<Function(String):Result<PathInfo,PathInfoError>>[inspectPath];
            let box:Api=Api{call:inspectPath};assert functions->length()==1;0"
           "type Api=product{call:Function(String):Result<PathInfo,PathInfoError>;};"))
         (mognitio.io::*path-inspection-fault-hook* (lambda () (error "Storage performed I/O"))))
    (multiple-value-bind (out err code) (v12-driver manifest) (same "" out) (same "" err) (same 0 code))
    (multiple-value-bind (out err code trace) (v12-trace (v12-native manifest))
      (same "" out) (same "" err) (same 0 code) (is (not (search "newfstatat(" trace))))))

(deftest v150-resource-nonaccumulation
  (let* ((manifest (v150-manifest "var i:Int=0;loop while(i<60){discard inspectPath(\"/\");discard inspectPath(\"/absent-mognitio-v150\");i=i+1;};0"))
         (before (v11-fd-snapshot)))
    (multiple-value-bind (out err code) (v12-driver manifest) (same "" out) (same "" err) (same 0 code))
    (same before (v11-fd-snapshot))
    (multiple-value-bind (out err code trace)
        (v12-trace (v12-native manifest '(:stress t :validate t :arena-unit 4096 :cap 65536)))
      (same "" out) (same "" err) (same 0 code)
      (let ((lines (uiop:split-string trace :separator '(#\Newline))))
        (same 120 (count-if (lambda (line) (search "newfstatat(" line)) lines))
        (same 60 (count-if (lambda (line) (and (search "munmap(" line) (search ", 2)" line))) lines))
        (is (not (search "close(3)" trace)))))))
