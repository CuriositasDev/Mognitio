(in-package #:mognitio.tests)

(deftest v160-large-live-graph-collection-bound
  ;; Independent operational bound: retain one million cells while allocating
  ;; and dropping one million more. Geometry overrides provide the slow control.
  (let* ((source (uiop:read-file-string (root-path "tests/fixtures/v160-live-arena.mgn")))
         (manifest (project-fixture (list (cons "app.mgn" source))))
         (original (fdefinition 'v12-native)))
    (dolist (fixed '(nil 1048576))
      (let ((image
              (replacing (v12-native
                          (lambda (input &optional options)
                            (funcall original input
                              (append options (when fixed (list :arena-unit fixed))))))
                (v110-counter-image manifest))))
        (multiple-value-bind (out bytes code)
            (process-result (list (namestring image)) :binary-error t :timeout 120)
          (same 0 code) (same "" out) (same 240 (length bytes))
          (flet ((word (offset)
                   (loop for i below 8 sum (ash (aref bytes (+ offset i)) (* i 8)))))
            (same 3000002 (word 32))
            (is (<= (word 72) (* 128 1024 1024)))
            (is (> (word 48) 0))
            (if fixed
                (is (> (word 48) 48))
                (is (<= (word 48) 48)))
            (format t "LIVE_ARENA fixed=~S collections=~D mapped=~D~%"
              fixed (word 48) (word 72))))))))

(deftest v160-nearly-full-live-graph-reserve
  ;; The retained graph sits just below an arena boundary. Reclaiming a few
  ;; cells must not suppress growth and cause thousands of full collections.
  (let* ((source (uiop:read-file-string (root-path "tests/fixtures/v160-low-reserve.mgn")))
         (manifest (project-fixture (list (cons "app.mgn" source))))
         (original (fdefinition 'v12-native)))
    (dolist (fixed '(nil 1048576))
      (let ((image
              (replacing (v12-native
                          (lambda (input &optional options)
                            (funcall original input
                              (append options (when fixed (list :arena-unit fixed))))))
                (v110-counter-image manifest))))
        (multiple-value-bind (out bytes code)
            (process-result (list (namestring image) (make-string 10800 :initial-element #\x))
                            :binary-error t :timeout 120)
          (same 0 code) (same "" out) (same 240 (length bytes))
          (flet ((word (offset)
                   (loop for i below 8 sum (ash (aref bytes (+ offset i)) (* i 8)))))
            (same 121605 (word 32))
            (is (<= (word 72) (* 2 1024 1024)))
            (if fixed
                (is (> (word 48) 1000))
                (is (<= (word 48) 16)))
            (format t "LOW_RESERVE fixed=~S collections=~D mapped=~D~%"
              fixed (word 48) (word 72))))))))

(deftest v160-optional-reserve-mapping-failure
  ;; mmap 1 creates the initial arena, 2 its metadata, and 3 the reserve.
  ;; Only the optional reserve mapping may fail while an existing block fits.
  (let* ((source (uiop:read-file-string (root-path "tests/fixtures/v160-low-reserve.mgn")))
         (manifest (project-fixture (list (cons "app.mgn" source))))
         (image (v12-native manifest)))
    (dolist (ordinal '(1 2 3 4))
      (multiple-value-bind (out err code trace)
          (v12-trace image (format nil "mmap:error=ENOMEM:when=~D" ordinal)
                     (list (make-string 10800 :initial-element #\x)))
        (same "" out)
        (same (if (= ordinal 3) 0 4) code)
        (same (if (= ordinal 3) "" (format nil "runtime error: allocation failure~%")) err)
        (is (search "INJECTED" trace))))))
