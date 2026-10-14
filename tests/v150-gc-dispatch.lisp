(in-package #:mognitio.tests)

(defun v150-run-address-tree (forms candidate)
  (let ((code (coerce forms 'vector)) (labels (make-hash-table :test #'equal))
        (pc 0) (address 0) (comparison 0) (probes 0))
    (loop for form across code for i from 0
          when (eq (first form) :label) do (setf (gethash (second form) labels) i))
    (loop repeat 1000 do
      (let* ((form (aref code pc)) (op (first form)) (target nil))
        (incf pc)
        (case op
          (:label nil)
          (:lea-meta (setf address (second form)))
          (:cmp-reg (incf probes) (setf comparison (- address candidate)))
          (:jz (when (zerop comparison) (setf target (second form))))
          (:ja (when (plusp comparison) (setf target (second form))))
          (:jmp (setf target (second form)))
          (otherwise (error "Unexpected dispatch instruction ~S" form)))
        (when target
          (multiple-value-bind (position present) (gethash target labels)
            (if present (setf pc position) (return-from v150-run-address-tree (values target probes)))))))
    (error "Address dispatch did not terminate")))

(deftest v150-gc-address-tree-exactness-and-bound
  ;; The oracle is an exact association lookup, independent of tree generation.
  (dolist (size '(0 1 2 3 7 16 31 64 257))
    (dolist (base '(4096 9223372036854775808))
      (let* ((rows (loop for i below size collect (list (list :lea-meta (+ base (* i 16))) i)))
             (forms (mognitio.native.runtime::ordered-address-dispatch rows :rcx "PROBE" :missing))
             (bound (integer-length size)))
        (loop for candidate from (- base 1) to (+ base (* size 16) 1) do
          (let ((expected (or (loop for row in rows
                                   when (= candidate (second (first row))) return (list (second row)))
                              (list :missing))))
            (multiple-value-bind (actual probes) (v150-run-address-tree forms candidate)
              (same (first expected) actual)
              (is (<= probes bound)))))))))

(deftest v150-gc-many-descriptors-and-static-roots
  ;; Keep every distinct nominal shape live across collections. Each field is
  ;; a static text root, and each object must reach its own checked descriptor.
  (let* ((count 96)
         (source (with-output-to-string (s)
                   (dotimes (i count) (format s "type P~D=product{value:String;};" i))
                   (dotimes (i count) (format s "let p~D:P~D=P~D{value:~S};" i i i (format nil "root-~D" i)))
                   (dotimes (i count) (format s "assert{p~D->value==~S};" i (format nil "root-~D" i)))
                   (write-string "true" s))))
    (multiple-value-bind (out err code)
        (process-result (list (namestring (v06-runtime-artifact source
                                         '(:stress t :validate t :arena-unit 65536 :cap 131072))))
                        :timeout 120)
      (same (format nil "true~%") out) (same "" err) (same 0 code))))
