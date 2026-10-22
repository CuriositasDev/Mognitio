(in-package #:mognitio.tests)

(defun v170-machine-range-input (fixture &optional before after)
  ;; Read the production function, retaining the independent frozen traversal.
  (let* ((text (uiop:read-file-string
                 (root-path "compiler/mgnc/src/WholeMachineCheck/verify.mgn")))
         (start (search "let range:" text))
         (end (and start (search "let fragment:" text :start2 start))))
    (is (and start end))
    (let ((implementation (subseq text start end)))
      (when before
        (let ((position (search before implementation)))
          (is position)
          (is (not (search before implementation :start2 (1+ position))))
          (setf implementation
                (concatenate 'string (subseq implementation 0 position)
                             after (subseq implementation (+ position (length before)))))))
      (let ((manifest (project-fixture
                (list (cons "mgnc.mgn"
                  (concatenate 'string "namespace Mgnc;"
                    (uiop:read-file-string (root-path "tests/fixtures/v170-machine-range-reference.mgn"))
                    implementation (uiop:read-file-string (root-path fixture))))))))
        (put-text manifest (format nil "[project]~%name=\"mgnc\"~%root_namespace=\"Mgnc\"~%"))
        manifest))))

(deftest v170-machine-range-boundaries
  ;; Static independent expectations cover 320 cases for both implementations.
  (let ((image (v110-counter-image
          (v170-machine-range-input "tests/fixtures/v170-machine-range-boundaries.mgn"))))
    (multiple-value-bind (out bytes code)
        (process-result (list (namestring image)) :binary-error t :timeout 60)
      (same 0 code) (same "" out) (same 240 (length bytes)))))

(deftest v170-machine-range-mutation-controls
  (dolist (mutation '(("i<stop" "i<=stop") ("start<0=>0" "start<0=>1")))
    (let ((image (v110-counter-image
            (v170-machine-range-input "tests/fixtures/v170-machine-range-boundaries.mgn"
                                      (first mutation) (second mutation)))))
      (multiple-value-bind (out bytes code)
          (process-result (list (namestring image)) :binary-error t :timeout 60)
        (declare (ignore bytes))
        (same 5 code) (same "" out)))))

(deftest v170-machine-range-allocation-bound
  ;; Both paths verify every selected value. Full traversal exceeds the bound.
  (let ((image (v110-counter-image
          (v170-machine-range-input "tests/fixtures/v170-machine-range-cost.mgn")))
        (counts nil))
    (dolist (mode '("old" "current"))
      (multiple-value-bind (out bytes code)
          (process-result (list (namestring image) mode) :binary-error t :timeout 180)
        (same 0 code) (same "" out) (same 240 (length bytes))
        (let ((allocated (loop for i below 8 sum (ash (aref bytes (+ 40 i)) (* i 8)))))
          (push allocated counts)
          (format t "MACHINE_RANGE mode=~A allocated_bytes=~D~%" mode allocated))))
    (is (< (first counts) (* 8 1024 1024)))
    (is (> (second counts) (* 128 1024 1024)))))
