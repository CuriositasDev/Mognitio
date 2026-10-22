(in-package #:mognitio.tests)

(defun v170-map-project (source &optional old)
  (let ((manifest
          (project-fixture
            (list (cons "mgnc.mgn" (uiop:read-file-string (root-path source)))
                  (cons "Data/data.mgn" (uiop:read-file-string
                    (root-path "compiler/mgnc/src/Data/data.mgn")))
                  (cons "IntMap/map.mgn" (uiop:read-file-string
                    (root-path (if old "tests/fixtures/v170-int-map-ten-level.mgn"
                                   "compiler/mgnc/src/IntMap/map.mgn"))))))))
    (put-text manifest (format nil "[project]~%name=\"mgnc\"~%root_namespace=\"Mgnc\"~%"))
    manifest))

(defun v170-map-counters (image region size)
  (multiple-value-bind (stdout bytes code)
      (process-result (list (namestring image) region size) :binary-error t :timeout 180)
    (same 0 code) (same "" stdout) (same 240 (length bytes))
    (flet ((counter (offset)
             (loop for i below 8 sum (ash (aref bytes (+ offset i)) (* i 8)))))
      (values (counter 32) (counter 40) (counter 48)))))

(deftest v170-radix-boundaries-and-generation
  (multiple-value-bind (stdout stderr code)
      (process-result (list "python3" (namestring (root-path "tests/mgnc/generate-int-map.py")) "--check"))
    (same 0 code) (same "" stderr) (is (search "INT_MAP_REPRODUCIBLE" stdout)))
  ;; The frozen ten-level implementation and current module must agree on
  ;; missing keys, every radix digit, replacement, and persistent snapshots.
  (dolist (old '(t nil))
    (let ((image (v110-counter-image
                   (v170-map-project "tests/mgnc/harnesses/v170-int-map.mgn" old))))
      (multiple-value-bind (stdout stderr code)
          (process-result (list (namestring image)) :binary-error t :timeout 180)
        (same 0 code) (same 240 (length stderr))
        (same (format nil "V170_INT_MAP_OK boundaries=17 levels=12 updates=2048 dense_updates=1024 high_updates=64 snapshots=true~%") stdout)))))

(deftest v170-radix-allocation-bound
  (let ((old (v110-counter-image (v170-map-project "tests/fixtures/v170-int-map-cost.mgn" t)))
        (wide (v110-counter-image (v170-map-project "tests/fixtures/v170-int-map-cost.mgn"))))
    (dolist (region '("low" "expanded" "edge" "fallback"))
      (loop for size in '("small" "medium" "large") for count in '(64 256 1024) do
        (multiple-value-bind (old-count old-bytes) (v170-map-counters old region size)
          (multiple-value-bind (new-count new-bytes) (v170-map-counters wide region size)
            (format t "RADIX_ALLOCATION region=~A size=~D old=~D new=~D old_bytes=~D new_bytes=~D~%"
                    region count old-count new-count old-bytes new-bytes)
            (cond
              ((string= region "fallback")
               ;; The unchanged exact-key fallback still accepts all nonnegative
               ;; Int64 keys. Two additional shared blanks are the only new nodes.
               (is (<= new-count (+ old-count 4))))
              (t
               ;; Two updates and four queries per key remain linear below the
               ;; new boundary. Include initialization and allocator workspace.
               (is (<= new-count (+ (* 33 count) 100)))
               (is (<= new-bytes (+ (* 2048 count) 8192)))
               (if (string= region "low")
                   (progn (is (<= new-count (+ (ceiling (* old-count 6) 5) 16)))
                          (is (<= new-bytes (+ (ceiling (* old-bytes 6) 5) 4096))))
                   (progn (is (< new-count old-count))
                          (when (= count 1024) (is (> old-bytes (* 64 1024 1024))))))))))))))

(deftest v170-radix-forced-collection
  (let ((manifest (v170-map-project "tests/fixtures/v170-int-map-cost.mgn"))
        (original (symbol-function 'v12-native)))
    (replacing (v12-native (lambda (path options)
                            (funcall original path (append '(:stress t) options))))
      (let ((image (v110-counter-image manifest)))
        (dolist (region '("low" "expanded" "edge" "fallback"))
          (multiple-value-bind (count bytes collections) (v170-map-counters image region "tiny")
            (declare (ignore count bytes))
            (is (> collections 100))))))))
