(in-package #:mognitio.tests)

(defun v160-run-fit-code (code memory requested)
  ;; Interpret emitted machine forms; the oracle below uses an ordered block list.
  (let ((registers (make-hash-table)) (labels (make-hash-table :test #'equal))
        (pc 0) (comparison 0) (instructions (coerce (mognitio.object:code-unit-instructions code) 'vector)))
    (setf (gethash :r15 registers) 1024 (gethash :rsp registers) 8192
          (gethash 8200 memory) requested)
    (loop for instruction across instructions for index from 0
          when (eq (mognitio.machine:instruction-opcode instruction) :label)
            do (setf (gethash (first (mognitio.machine:instruction-operands instruction)) labels) index))
    (labels ((reg (name) (gethash name registers 0))
             (load-at (address)
               (multiple-value-bind (value found) (gethash address memory)
                 (unless found (error "Unmapped allocator read ~D" address)) value))
             (jump (target)
               (setf pc (or (gethash target labels) (error "Missing allocator label ~S" target)))))
      (loop repeat 200000 do
        (let* ((instruction (aref instructions pc))
               (op (mognitio.machine:instruction-opcode instruction))
               (args (mognitio.machine:instruction-operands instruction))
               (a (first args)) (b (second args)) (c (third args)))
          (incf pc)
          (case op
            (:label nil)
            (:load-word (setf (gethash a registers) (load-at (+ (reg b) c))))
            (:store-word (setf (gethash (+ (reg a) b) memory) (reg c)))
            (:lea-base (setf (gethash a registers) (+ (reg b) c)))
            (:mov-reg (setf (gethash a registers) (reg b)))
            (:imm-reg (setf (gethash a registers) b))
            (:imm-rax (setf (gethash :rax registers) a))
            (:imm-rdx (setf (gethash :rdx registers) a))
            (:add-imm (setf (gethash a registers) (+ (reg a) b)))
            (:add-reg (setf (gethash a registers) (+ (reg a) (reg b))))
            (:and-imm (setf (gethash a registers) (logand (reg a) b)))
            (:sub-reg (setf (gethash a registers) (- (reg a) (reg b))))
            (:cmp-imm (setf comparison (- (reg a) b)))
            (:cmp-reg (setf comparison (- (reg a) (reg b))))
            (:jmp (jump a))
            (:jz (when (zerop comparison) (jump a)))
            (:jnz (unless (zerop comparison) (jump a)))
            (:jb (when (minusp comparison) (jump a)))
            (:ja (when (plusp comparison) (jump a)))
            (:jae (unless (minusp comparison) (jump a)))
            (:ret (return-from v160-run-fit-code (reg :rax)))
            (otherwise (error "Unimplemented allocator instruction ~S" op)))))
      (error "Allocator instruction budget exceeded"))))

(defun v160-fit-sequence (sizes requests &optional code reset-at)
  (let* ((memory (make-hash-table)) (oracle nil) (address 16384)
         (head (+ 1024 288))
         (mognitio.native.runtime::*test-options* '(:gc-counters t))
         (code (or code (mognitio.native.runtime::find-free-unit))))
    ;; Deliberately use the independently pinned production v8 geometry.
    (loop for at from 1024 below (+ 1024 944) by 8 do (setf (gethash at memory) 0))
    (dolist (size sizes)
      (push (list address size) oracle)
      (setf (gethash address memory) size (gethash (+ address 8) memory) 0
            (gethash (+ address 16) memory) 0 (gethash (+ address 24) memory) 0)
      (incf address (+ size 64)))
    (setf oracle (nreverse oracle) (gethash head memory) (caar oracle))
    (loop for rest on oracle
          do (setf (gethash (+ (caar rest) 16) memory) (or (caadr rest) 0)))
    (loop for requested in requests for ordinal from 0 do
      (when (eql ordinal reset-at)
        ;; Collection invalidates cursor links; historical size keys may remain.
        (loop for at from 304 below 688 by 8 do
          (setf (gethash (+ 1024 at) memory) 0)))
      (let* ((selected (find-if (lambda (row) (>= (second row) requested)) oracle))
             (expected (or (first selected) 0))
             (actual (v160-run-fit-code code memory requested)))
        (same expected actual)
        (when selected
          (let* ((size (second selected)) (remaining (- size requested))
                 (split (>= remaining 40)))
            (same 1 (gethash (+ expected 8) memory))
            (same (if split requested size) (gethash expected memory))
            (setf oracle (loop for row in oracle append
              (if (eq row selected)
                  (when split (list (list (+ expected requested) remaining)))
                  (list row))))))
        (let ((pointer (gethash head memory)) (visited nil))
          (dolist (row oracle)
            (same (first row) pointer) (same (second row) (gethash pointer memory))
            (same 0 (gethash (+ pointer 8) memory))
            (is (not (member pointer visited)))
            (push pointer visited) (setf pointer (gethash (+ pointer 16) memory)))
          (same 0 pointer))))
    (gethash (+ 1024 112) memory)))

(deftest v160-fit-cursor-first-fit-equivalence
  (v160-fit-sequence '(40 40 40 4096) '(80 40 40 40 80 32 48 56 160 168 40))
  (v160-fit-sequence '(120 4096) '(160 40 160 40 160 80))
  (let ((seed 121) (sizes nil) (requests nil))
    (dotimes (index 96)
      (setf seed (mod (+ (* seed 1103515245) 12345) 2147483648))
      (push (+ 32 (* 8 (mod seed 40))) sizes))
    (dotimes (index 256)
      (setf seed (mod (+ (* seed 1103515245) 12345) 2147483648))
      (push (+ 32 (* 8 (mod seed 48))) requests))
    (v160-fit-sequence (append sizes '(65536)) requests)))

(deftest v160-fit-cursor-bounded-repeated-prefix
  (let* ((sizes (append (make-list 256 :initial-element 40) '(65536)))
         (requests (make-list 256 :initial-element 80))
         (probes (v160-fit-sequence sizes requests)))
    (is (<= probes 512))
    ;; Removing cache reuse keeps allocation results but loses the scan bound.
    (let* ((mognitio.native.runtime::*test-options* '(:gc-counters t))
           (code (mognitio.native.runtime::find-free-unit)))
      (setf (mognitio.object:code-unit-instructions code)
        (mapcar (lambda (instruction)
          (if (and (eq (mognitio.machine:instruction-opcode instruction) :load-word)
                   (equal (mognitio.machine:instruction-operands instruction) '(:r11 :r10 0)))
              (first (machine '(:imm-reg :r11 0))) instruction))
          (mognitio.object:code-unit-instructions code)))
      (is (> (v160-fit-sequence sizes requests code) 512)))))

(deftest v160-fit-cursor-owner-removal-mutation
  (replacing (mognitio.native.runtime::repair-fit-cursors (lambda () nil))
    (signals error (v160-fit-sequence '(40 40 40 4096) '(80 40 40 40 80)))))


(deftest v160-large-fit-cursor-equivalence-and-collisions
  ;; 1184 and 928 share a cache set. The earlier 1000-byte block becomes
  ;; eligible for the smaller request, so a stale cursor would violate first-fit.
  (v160-fit-sequence '(1000 8192) '(1184 928 1184 928 40 168))
  (v160-fit-sequence '(40 40 40 8192) '(1184 40 40 40 1184 1312 928))
  (let ((seed 8461) (sizes nil) (requests nil))
    (dotimes (index 128)
      (setf seed (mod (+ (* seed 1103515245) 12345) 2147483648))
      (push (+ 32 (* 8 (mod seed 512))) sizes))
    (dotimes (index 512)
      (setf seed (mod (+ (* seed 1103515245) 12345) 2147483648))
      (push (+ 32 (* 8 (mod seed 1024))) requests))
    (v160-fit-sequence (append sizes '(4194304)) requests)))

(deftest v160-large-fit-cursor-bounded-repeated-prefix
  (let* ((sizes (append (make-list 256 :initial-element 40) '(1048576)))
         (requests (loop repeat 256 append '(1184 1312))))
    (is (<= (v160-fit-sequence sizes requests) 1024))
    ;; Disabling cursor reuse preserves values but fails the operational bound.
    (let* ((mognitio.native.runtime::*test-options* '(:gc-counters t))
           (code (mognitio.native.runtime::find-free-unit)))
      (setf (mognitio.object:code-unit-instructions code)
        (mapcar (lambda (instruction)
          (if (and (eq (mognitio.machine:instruction-opcode instruction) :load-word)
                   (equal (mognitio.machine:instruction-operands instruction) '(:r11 :r10 0)))
              (first (machine '(:imm-reg :r11 0))) instruction))
          (mognitio.object:code-unit-instructions code)))
      (is (> (v160-fit-sequence sizes requests code) 1024)))))

(deftest v160-large-fit-cursor-collision-and-owner-mutants
  (let* ((mognitio.native.runtime::*test-options* '(:gc-counters t))
         (code (mognitio.native.runtime::find-free-unit)))
    (setf (mognitio.object:code-unit-instructions code)
      (mapcar (lambda (instruction)
        (if (and (eq (mognitio.machine:instruction-opcode instruction) :cmp-reg)
                 (equal (mognitio.machine:instruction-operands instruction) '(:r11 :rcx)))
            (first (machine '(:cmp-reg :rcx :rcx))) instruction))
        (mognitio.object:code-unit-instructions code)))
    (signals error (v160-fit-sequence '(1000 8192) '(1184 928) code)))
  (replacing (mognitio.native.runtime::repair-fit-cursors (lambda () nil))
    (signals error (v160-fit-sequence '(40 40 40 8192) '(1184 40 40 40 1184)))))

(deftest v160-large-fit-native-collection-reuse
  ;; Large byte objects alternate with small headers across repeated collections.
  ;; A bounded heap forces coalescing while the original argument stays live.
  (let* ((source (uiop:read-file-string (root-path "tests/fixtures/v160-large-fit-gc.mgn")))
         (manifest (project-fixture (list (cons "app.mgn" source))))
         (original (fdefinition 'v12-native)))
    (dolist (options '((:arena-unit 4096 :cap 65536 :validate t :gc-counters t)
                       (:arena-unit 4096 :cap 65536 :validate t :gc-counters t :stress t)))
      (let ((image (replacing (v12-native
                            (lambda (input &optional ignored)
                              (declare (ignore ignored))
                              (funcall original input options)))
                      (v110-counter-image manifest))))
        (multiple-value-bind (out bytes code)
            (process-result (list (namestring image) (make-string 640 :initial-element #\x))
                            :binary-error t :timeout 120)
          (same 0 code) (same "" out) (same 240 (length bytes))
          (is (> (loop for i below 8 sum (ash (aref bytes (+ 48 i)) (* i 8))) 0)))))))


(defun v170-mutated-fit-code (before after)
  (let* ((mognitio.native.runtime::*test-options* '(:gc-counters t))
         (code (mognitio.native.runtime::find-free-unit)) (matches 0))
    (setf (mognitio.object:code-unit-instructions code)
      (mapcar (lambda (instruction)
        (if (equal (cons (mognitio.machine:instruction-opcode instruction)
                         (mognitio.machine:instruction-operands instruction)) before)
            (progn (incf matches) (first (machine after))) instruction))
        (mognitio.object:code-unit-instructions code)))
    (same 1 matches) code))

(deftest v170-two-way-fit-first-fit-and-reset
  ;; Independent ordered-block selection and complete free-chain checks cover
  ;; promotions, eviction, smaller colliding requests and owner-link removal.
  (dolist (count '(0 1 2 7 31 64 257))
    (dolist (pattern '((40) (40 80 160) (416) (40 416 80)
                       (40 1184 160) (1000 1000 40)))
      (let ((sizes (append (loop for i below count
                                collect (nth (mod i (length pattern)) pattern))
                           '(65536))))
        (dolist (requests '((1184 416 1184 416 1184 416 1184 416)
                            (416 1184 416 1184 416 1184 416 1184)
                            (1184 40 416 80 1184 160 416 40)
                            (696 440 184 696 440 184 160 40)
                            (928 1184 928 1184 928 1184 928 1184)
                            (1184 416 672 1184 416 672 160 40)))
          (dolist (reset '(nil 3))
            (v160-fit-sequence sizes requests nil reset)))))))

(deftest v170-two-way-fit-collision-work-bound
  ;; Two cold traversals suffice for two colliding sizes. Later exact hits
  ;; must not rescan the unchanged prefix, independently of allocation values.
  (let* ((sizes (append (make-list 2048 :initial-element 40) '(1048576)))
         (requests (loop repeat 32 append '(1184 416)))
         (bound (+ (* 2 2049) 62)))
    (is (<= (v160-fit-sequence sizes requests) bound))
    (let ((disabled (v170-mutated-fit-code '(:load-word :r11 :r10 0)
                                          '(:imm-reg :r11 0))))
      (is (> (v160-fit-sequence sizes requests disabled) bound)))))

(deftest v170-two-way-fit-owner-and-pair-mutations
  ;; Check mutation membership outside the expected rejection boundary.
  (let ((first-owner (v170-mutated-fit-code '(:cmp-reg :r11 :rcx) '(:cmp-reg :rcx :rcx)))
        (second-owner (v170-mutated-fit-code '(:cmp-reg :rdx :rcx) '(:cmp-reg :rcx :rcx)))
        (pair (v170-mutated-fit-code '(:store-word :r10 0 :rax) '(:store-word :r10 0 :r9))))
    (signals error (v160-fit-sequence '(1000 1000 40 65536) '(1184 928) first-owner))
    (signals error (v160-fit-sequence '(1000 1000 40 65536) '(1184 1312 928) second-owner))
    (signals error (v160-fit-sequence '(1000 1000 40 65536) '(928 1184 928) pair))))
