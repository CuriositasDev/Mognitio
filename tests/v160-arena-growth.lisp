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
            (is (<= (word 72) (* 160 1024 1024)))
            (is (> (word 48) 0))
            (if fixed
                (is (> (word 48) 48))
                (is (<= (word 48) 48)))
            (format t "LIVE_ARENA fixed=~S collections=~D mapped=~D~%"
              fixed (word 48) (word 72))))))))
