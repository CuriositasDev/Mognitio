(in-package #:mognitio.tests)

(deftest v170-buffered-encoding-allocation-bound
  ;; Compile the actual carry implementation and verify every resulting byte.
  ;; The direct-carry control has identical values but exceeds the work bound.
  (let* ((files
           (loop for name in '("Data/data.mgn" "Tables/update.mgn" "EncodeChunks/chunks.mgn")
                 collect (cons name (uiop:read-file-string
                   (root-path (concatenate 'string "compiler/mgnc/src/" name))))))
         (manifest (project-fixture
           (cons (cons "mgnc.mgn" (uiop:read-file-string
                   (root-path "tests/fixtures/v170-encode-buffer-cost.mgn"))) files))))
    (put-text manifest (format nil "[project]~%name=\"mgnc\"~%root_namespace=\"Mgnc\"~%"))
    (let ((image (v110-counter-image manifest)))
      (dolist (size '("small" "medium" "large"))
        (let ((counts nil))
          (dolist (mode '("direct" "buffered"))
            (multiple-value-bind (out bytes code)
                (process-result (list (namestring image) mode size)
                                :binary-error t :timeout 300)
              (same 0 code) (same "" out) (same 240 (length bytes))
              (let ((allocations (loop for i below 8
                                       sum (ash (aref bytes (+ 32 i)) (* i 8)))))
                (push allocations counts)
                (format t "ENCODE_BUFFER size=~A mode=~A allocations=~D~%"
                        size mode allocations))))
          (is (< (first counts) (second counts)))
          (when (string= size "large")
            (is (<= (first counts) 1000000))
            (is (> (second counts) 1000000))))))))
