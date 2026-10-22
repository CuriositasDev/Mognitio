(in-package #:mognitio.tests)

(deftest v170-buffered-encoding-allocation-bound
  ;; All three paths verify every byte. The frozen flat-prefix control keeps
  ;; allocation counts low but exposes repeated growing-prefix byte copies.
  (let* ((files
           (append
             (loop for name in '("Data/data.mgn" "Tables/update.mgn" "EncodeChunks/chunks.mgn")
                   collect (cons name (uiop:read-file-string
                     (root-path (concatenate 'string "compiler/mgnc/src/" name)))))
             (list (cons "FlatChunks/chunks.mgn" (uiop:read-file-string
                      (root-path "tests/fixtures/v170-encode-flat-reference.mgn"))))))
         (manifest (project-fixture
           (cons (cons "mgnc.mgn" (uiop:read-file-string
                   (root-path "tests/fixtures/v170-encode-buffer-cost.mgn"))) files))))
    (put-text manifest (format nil "[project]~%name=\"mgnc\"~%root_namespace=\"Mgnc\"~%"))
    (let ((image (v110-counter-image manifest)))
      (dolist (size '("small" "medium" "large"))
        (let ((counts nil) (totals nil))
          (dolist (mode '("direct" "flat" "buffered"))
            (multiple-value-bind (out bytes code)
                (process-result (list (namestring image) mode size)
                                :binary-error t :timeout 300)
              (same 0 code) (same "" out) (same 240 (length bytes))
              (flet ((counter (offset)
                       (loop for i below 8 sum (ash (aref bytes (+ offset i)) (* i 8)))))
                (push (counter 32) counts) (push (counter 40) totals)
                (format t "ENCODE_BUFFER size=~A mode=~A allocations=~D allocated_bytes=~D~%"
                        size mode (first counts) (first totals)))))
          (is (< (first counts) (third counts)))
          (is (< (first totals) (second totals)))
          (when (string= size "large")
            (is (<= (first counts) 1000000))
            (is (> (third counts) 1000000))
            (is (< (first totals) (* 64 1024 1024)))
            (is (> (second totals) (* 128 1024 1024)))))))))
