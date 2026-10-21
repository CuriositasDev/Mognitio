(in-package #:mognitio.tests)

(deftest v170-large-heap-reserve-boundaries
  ;; Interpret the actual unsigned policy branches. The independent oracle
  ;; covers each threshold, cap saturation and both halves of the word range.
  (let* ((mognitio.native.runtime::*test-options* nil)
         (forms (v170-arena-forms #'mognitio.native.runtime::allocate-unit))
         (mapped-values '(0 1 1048576 134217727 134217728 134217729 268435456
                          536870911 536870912 536870913 1073741823 1073741824
                          1073741825 2147483648 4294967296 8589934592
                          9223372036854775807 9223372036854775808
                          18446744073709551614 18446744073709551615)))
    (dolist (labels '((:reserve-large-cap . :reserve-sized)
                     (:growth-large-cap . :growth-clamped)))
      (let* ((branch (position (list :ja (car labels)) forms :test #'equal))
             (end (position (list :label (cdr labels)) forms :test #'equal)))
        (is branch) (is end)
        (let ((selected (subseq forms (- branch 2) (1+ end))))
          (labels ((run (code mapped)
                     (let ((memory (make-hash-table)))
                       (setf (gethash (+ 4096 72) memory) mapped)
                       (v170-arena-vm code memory
                         (list (cons :rax (floor mapped 8)) (cons :r15 4096))
                         :stop (cdr labels))))
                   (expected (mapped)
                     (min (floor mapped 8)
                          (if (> mapped 536870912) 134217728 16777216))))
            (dolist (mapped mapped-values)
              (same (expected mapped) (run selected mapped)))
            (dolist (mutation
                      (list (list (list :ja (car labels)) (list :jae (car labels)) 536870912)
                            (list '(:imm-rax 134217728) '(:imm-rax 268435456) 8589934592)
                            (list '(:imm-rax 16777216) '(:imm-rax 33554432) 536870912)))
              (destructuring-bind (before after mapped) mutation
                (same 1 (count before selected :test #'equal))
                (let ((mutant (substitute after before selected :test #'equal)))
                  (is (/= (expected mapped) (run mutant mapped))))))))))
    (dolist (options '((:arena-unit 4096) (:cap 65536)))
      (let* ((mognitio.native.runtime::*test-options* options)
             (fixed (v170-arena-forms #'mognitio.native.runtime::allocate-unit)))
        (is (not (member '(:label :reserve-large-cap) fixed :test #'equal)))
        (is (not (member '(:label :growth-large-cap) fixed :test #'equal)))))))

(deftest v170-large-live-graph-reserve-control
  ;; Cross the adaptive threshold with a retained graph, then drop another
  ;; twelve million objects. Disabling the two large-heap branches preserves
  ;; values and allocation counts but exceeds the collection-work bound.
  (let* ((source (uiop:read-file-string (root-path "tests/fixtures/v170-live-reserve.mgn")))
         (manifest (project-fixture (list (cons "app.mgn" source))))
         (original (fdefinition 'mognitio.native.runtime::allocate-unit)))
    (dolist (disabled '(nil t))
      (let ((image
              (replacing (mognitio.native.runtime::allocate-unit
                          (lambda ()
                            (let* ((unit (funcall original))
                                   (instructions (mognitio.object:code-unit-instructions unit))
                                   (targets '(:runtime/allocate-block/reserve-large-cap
                                              :runtime/allocate-block/growth-large-cap)))
                              (when disabled
                                (same 2 (count-if
                                  (lambda (inst)
                                    (and (eq (mognitio.machine:instruction-opcode inst) :ja)
                                         (member (first (mognitio.machine:instruction-operands inst)) targets)))
                                  instructions))
                                (setf (mognitio.object:code-unit-instructions unit)
                                  (remove-if
                                    (lambda (inst)
                                      (and (eq (mognitio.machine:instruction-opcode inst) :ja)
                                           (member (first (mognitio.machine:instruction-operands inst)) targets)))
                                    instructions)))
                              unit)))
                (v110-counter-image manifest))))
        (multiple-value-bind (out bytes code)
            (process-result (list (namestring image)) :binary-error t :timeout 300)
          (same 0 code) (same "" out) (same 240 (length bytes))
          (flet ((word (offset)
                   (loop for i below 8 sum (ash (aref bytes (+ offset i)) (* i 8)))))
            (same 36000002 (word 32))
            (is (> (word 72) 1073741824))
            (is (<= (word 72) (* 1536 1024 1024)))
            (if disabled (is (> (word 48) 80)) (is (<= (word 48) 80)))
            (format t "LARGE_RESERVE disabled=~S collections=~D mapped=~D~%"
                    disabled (word 48) (word 72))))))))
