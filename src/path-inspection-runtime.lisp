(in-package #:mognitio.io)

;; Device/inode are unsigned OS scalars, never language Int or GC references.
(defstruct (file-identity (:constructor %file-identity (device inode)))
  (device 0 :type (unsigned-byte 64) :read-only t)
  (inode 0 :type (unsigned-byte 64) :read-only t))
(defun file-identity-equal (a b)
  (and (= (file-identity-device a) (file-identity-device b))
       (= (file-identity-inode a) (file-identity-inode b))))
(defun file-identity-not-equal (a b) (not (file-identity-equal a b)))
(defvar *path-inspection-fault-hook* nil)
(defun inspection-errno-kind (errno)
  (case errno (36 0) (2 2) ((1 13) 3) ((20 95) 4) ((12 23 24 28 122) 6) (otherwise 7)))
(defun inspection-status (status)
  (unless (and (integerp status) (<= -4095 status 0) (not (member status '(-9 -14 -22))))
    (mognitio.diagnostics:internal-error "Invalid path inspection runtime state"))
  status)
(defun inspect-path-value (text)
  (let* ((path (directory-path-bytes text)) (end (1- (length path)))
         (stat (make-array 144 :element-type '(unsigned-byte 8) :initial-element 0)))
    ;; Preserve interior components. Slash-only names reduce to one slash.
    (loop while (and (> end 1) (= (aref path (1- end)) 47)) do (decf end))
    (setf (aref path end) 0)
    (mognitio.runtime::allocation-point :path-inspection)
    (sb-sys:with-pinned-objects (path stat)
      (loop
        for injected = (and *path-inspection-fault-hook* (funcall *path-inspection-fault-hook*))
        for status = (inspection-status
                       (or injected
                           (if (zerop (directory-fstatat -100 (sb-sys:vector-sap path)
                                                         (sb-sys:vector-sap stat) 256))
                               0 (- (sb-sys:sap-ref-32 (directory-errno) 0)))))
        unless (= status -4) do
          (when (minusp status) (directory-reject (inspection-errno-kind (- status))))
          (let* ((sap (sb-sys:vector-sap stat))
                 (kind (case (logand #o170000 (sb-sys:sap-ref-32 sap 24))
                         (#o100000 0) (#o040000 1) (#o120000 2) (otherwise 3)))
                 (device (sb-sys:sap-ref-64 sap 0)) (inode (sb-sys:sap-ref-64 sap 8)))
            (mognitio.runtime::allocation-point :file-identity)
            (return (values kind (%file-identity device inode))))))))
(defun invoke-path-inspection (text result error-type info-type kind-type entry-kind)
  (handler-case
      (multiple-value-bind (kind identity) (inspect-path-value text)
        (mognitio.value:construct result 0
          (mognitio.value:construct info-type 0
            (mognitio.value:construct entry-kind kind) identity)))
    (directory-failure (condition)
      (mognitio.value:construct result 1
        (mognitio.value:construct error-type 0
          (mognitio.value:construct kind-type (io-failure-kind condition)) text)))
    (storage-condition () (mognitio.runtime:runtime-error :allocation-failed))))
