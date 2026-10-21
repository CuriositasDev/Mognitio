(in-package #:mognitio.tests)

(defun v170-arena-forms (producer &rest args)
  (let ((original (fdefinition 'mognitio.native.runtime::runtime-unit)) (captured nil))
    (replacing (mognitio.native.runtime::runtime-unit
                (lambda (name forms &optional (kind :runtime))
                  (setf captured forms) (funcall original name forms kind)))
      (apply producer args))
    captured))

(defun v170-arena-vm (forms memory initial &key start stop (limit 2000000))
  ;; Interpret actual emitted operations against an independent address map.
  ;; An unmapped read fails the test, including a premature candidate dereference.
  (let ((code (coerce forms 'vector)) (labels (make-hash-table :test #'eq))
        (registers (make-hash-table :test #'eq)) (pc 0) (comparison 0) (probes 0))
    (loop for form across code for i from 0 when (eq (first form) :label)
          do (setf (gethash (second form) labels) i))
    (dolist (pair initial) (setf (gethash (car pair) registers) (cdr pair)))
    (when start (setf pc (gethash start labels)))
    (labels ((reg (name) (gethash name registers 0))
             (write-reg (name value) (setf (gethash name registers) (mod value (ash 1 64))))
             (read-memory (address)
               (multiple-value-bind (value present) (gethash address memory)
                 (unless present (error "Arena oracle read unmapped address ~X" address)) value)))
      (loop repeat limit do
        (destructuring-bind (op &rest args) (aref code pc)
          (incf pc)
          (let ((target nil))
            (case op
              (:label (when (eq (first args) stop)
                        (return-from v170-arena-vm (values (reg :rax) probes memory))))
              (:jmp (setf target (first args)))
              (:jz (when (zerop comparison) (setf target (first args))))
              (:jnz (unless (zerop comparison) (setf target (first args))))
              (:jb (when (minusp comparison) (setf target (first args))))
              (:jbe (when (<= comparison 0) (setf target (first args))))
              (:ja (when (> comparison 0) (setf target (first args))))
              (:jae (when (>= comparison 0) (setf target (first args))))
              (:load-word (write-reg (first args) (read-memory (+ (reg (second args)) (third args)))))
              (:load-byte (write-reg (first args) (logand 255 (read-memory (+ (reg (second args)) (third args))))))
              (:store-word (setf (gethash (+ (reg (first args)) (second args)) memory) (reg (third args))))
              (:load-frame (write-reg (first args) (read-memory (+ (reg :rbp) (second args)))))
              (:store-frame (setf (gethash (+ (reg :rbp) (first args)) memory) (reg (second args))))
              (:mov-reg (write-reg (first args) (reg (second args))))
              (:imm-rax (write-reg :rax (first args)))
              (:mov-edi (write-reg :rdi (first args)))
              (:mov-eax (write-reg :rax (first args)))
              (:add-reg (write-reg (first args) (+ (reg (first args)) (reg (second args)))))
              (:sub-reg (write-reg (first args) (- (reg (first args)) (reg (second args)))))
              (:add-imm (write-reg (first args) (+ (reg (first args)) (second args))))
              (:shr-imm (write-reg (first args) (ash (reg (first args)) (- (second args)))))
              (:and-imm (write-reg (first args) (logand (reg (first args)) (second args))))
              (:cmp-imm (setf comparison (- (reg (first args)) (second args))))
              (:cmp-reg
               (when (equal args '(:rdx :r10)) (incf probes))
               (setf comparison (- (reg (first args)) (reg (second args)))))
              (:test (setf comparison (reg :rax)))
              (:test-rcx (setf comparison (reg :rcx)))
              (:ret (return-from v170-arena-vm (values (reg :rax) probes memory)))
              (:syscall
               (same 60 (reg :rax)) (same 3 (reg :rdi))
               (return-from v170-arena-vm (values -3 probes memory)))
              (otherwise (error "Unexpected arena oracle instruction ~S" (cons op args))))
            (when target (setf pc (or (gethash target labels) (error "Missing arena label ~S" target)))))))
      (error "Arena oracle did not terminate"))))

(defun v170-arena-memory (rows &optional (candidate 0))
  (let ((memory (make-hash-table :test #'eql)) (workspace #x200000) (stack #x100000)
        (frame #x300000) (queue 256))
    (setf (gethash (+ stack 8) memory) candidate
          (gethash (+ stack 16) memory) workspace
          (gethash (+ workspace 8) memory) queue
          (gethash (+ workspace 24) memory) (length rows)
          (gethash (- frame 8) memory) queue
          (gethash (- frame 24) memory) workspace
          (gethash (- frame 32) memory) (length rows))
    (loop for row in rows for i from 0 for address = (+ workspace queue 32 (* i 24)) do
      (loop for value in row for offset from 0 by 8 do (setf (gethash (+ address offset) memory) value))
      (destructuring-bind (base size bitmap) row
        (loop for byte below (/ size 8) do (setf (gethash (+ bitmap byte) memory) 0))
        (setf (gethash (+ bitmap 4) memory) 1 (gethash (+ base 40) memory) 1)))
    (values memory (list (cons :rsp stack) (cons :rbp frame)))))

(deftest v170-gc-arena-index-sort-and-pointer-oracle
  (let* ((mognitio.native.runtime::*test-options* nil)
         (sorter (v170-arena-forms #'mognitio.native.runtime::gc-workspace-unit))
         (validator (v170-arena-forms #'mognitio.native.runtime::validate-root-unit 0)))
    (dolist (count '(0 1 2 3 7 16 31 64 257))
      (dolist (base '(4096 9223372036854775808))
        (let* ((rows (loop for i below count collect (list (+ base (* i 256)) (+ 64 (* 8 (mod i 9))) (+ #x40000000 (* i 4096)))))
               (orders (list rows (reverse rows)
                             (append (loop for row in rows for i from 0 when (oddp i) collect row)
                                     (loop for row in rows for i from 0 when (evenp i) collect row)))))
          (dolist (order orders)
            (multiple-value-bind (memory registers) (v170-arena-memory order)
              (v170-arena-vm sorter memory registers :start :indexed :stop :sort-done)
              (same rows (loop for i below count collect
                          (loop for offset in '(0 8 16) collect (gethash (+ #x200000 256 32 (* i 24) offset) memory))))))
          (dolist (candidate (remove-duplicates
                              (append (list (1- base) base (+ base (* count 256) 1))
                                (loop for row in rows append
                                  (loop for offset in (list 7 8 31 32 33 40 (1- (second row)) (second row))
                                        collect (+ (first row) offset))))))
            ;; Linear exact-start association is independent of both sorting
            ;; and the binary range search in the emitted validator.
            (let ((expected (if (find candidate rows :key (lambda (row) (+ (first row) 32))) 1 -3)))
              (multiple-value-bind (memory registers) (v170-arena-memory rows candidate)
                (multiple-value-bind (actual probes) (v170-arena-vm validator memory registers)
                  (same expected actual) (is (<= probes (integer-length count))))))))))))

(deftest v170-gc-arena-index-oracle-negative-controls
  (let* ((mognitio.native.runtime::*test-options* nil)
         (rows '((4096 64 1073741824) (4352 64 1073745920) (4608 64 1073750016)))
         (sorter (v170-arena-forms #'mognitio.native.runtime::gc-workspace-unit))
         (validator (v170-arena-forms #'mognitio.native.runtime::validate-root-unit 0))
         (wrong-search (subst '(:jae :lower) '(:jb :lower) validator :test #'equal))
         (wrong-bitmap (subst '(:store-word :rsi 8 :rax) '(:store-word :rsi 16 :rax) sorter :test #'equal)))
    (signals error
      (multiple-value-bind (memory registers) (v170-arena-memory rows 4128)
        (same 1 (v170-arena-vm wrong-search memory registers))))
    (signals error
      (multiple-value-bind (memory registers) (v170-arena-memory (reverse rows))
        (v170-arena-vm wrong-bitmap memory registers :start :indexed :stop :sort-done)
        (same rows (loop for i below 3 collect
                    (loop for offset in '(0 8 16) collect (gethash (+ #x200000 256 32 (* i 24) offset) memory))))))))
