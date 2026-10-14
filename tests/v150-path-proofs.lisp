(in-package #:mognitio.tests)

(deftest v150-native-full-width-comparison
  ;; Exercise the production helper with synthetic unsigned OS words, outside
  ;; the public language (which intentionally cannot construct FileIdentity).
  (dolist (op '(:file-identity.equal :file-identity.not-equal))
    (let* ((inst (mognitio.ir:make-instruction :op op :type :bool))
           (unit (mognitio.native.runtime::file-identity-equality-unit inst))
           (forms (append (mognitio.native.runtime::helper-frame 16)
                    (loop for (a b c d equal) in
                          '((0 0 0 0 t) (0 1 1 1 nil) (1 0 1 1 nil)
                            (4294967296 0 0 0 nil) (0 4294967296 0 0 nil)
                            (9223372036854775808 0 0 0 nil) (0 9223372036854775808 0 0 nil)
                            (18446744073709551615 18446744073709551615 18446744073709551615 18446744073709551615 t))
                          append
                      (append (loop for value in (list a b c d) for slot in '(-16 -8 -64 -56)
                                    append (list (list :imm-rax (if (logbitp 63 value) (- value (ash 1 64)) value)) (list :store-frame slot :rax)))
                              `((:lea-base :rax :rbp -48) (:store-out 0 :rax)
                                (:lea-base :rax :rbp -96) (:store-out 8 :rax)
                                (:call ,(mognitio.object:code-unit-entry unit))
                                (:cmp-imm :rax ,(if (eq (not (null equal)) (eq op :file-identity.equal)) 1 0))
                                (:jnz :failed))))
                    '((:mov-edi 0) (:mov-eax 60) (:syscall) (:ud2)
                      (:label :failed) (:mov-edi 1) (:mov-eax 60) (:syscall) (:ud2))))
           (instructions (append
                           (mapcar (lambda (f) (mognitio.machine:make-instruction :opcode (first f) :operands (rest f))) forms)
                           (mognitio.object:code-unit-instructions unit)))
           (image (put-bytes (fresh-path ".elf") (mognitio.elf:make-image (mognitio.amd64:encode instructions)))))
      (mognitio.native.runtime::verify-file-identity-equality-unit unit)
      (sb-posix:chmod image #o700)
      (multiple-value-bind (out err code) (process-result (list (namestring image)))
        (same "" out) (same "" err) (same 0 code)))))

(deftest v150-machine-proof-mutations
  (dolist (mutation '(:nofollow :device :inode :roots :cleanup :identity-root :comparison-word))
    (let* ((ir (mognitio.ir:lower-program (project-checked (v150-manifest
                  (format nil "let p:PathInfo=~A;assert p->identity==p->identity;0" (v150-info "/"))))))
           (mognitio.native.runtime::*runtime-module* ir) (units nil)
           (original (fdefinition 'mognitio.native.runtime::verify-io-units)))
      (replacing (mognitio.native.runtime::verify-io-units
                   (lambda (value) (setf units value) (funcall original value)))
        (mognitio.machine:lower-module ir))
      (let* ((unit (find-if (lambda (u)
                             (let* ((entry (mognitio.object:code-unit-entry u))
                                    (name (and (consp entry) (second entry))))
                               (and (consp name)
                                    (if (eq mutation :comparison-word) (eq (first name) :file-identity.equal)
                                        (eq (third name) :inspect-path))))) units))
             (instructions (mognitio.object:code-unit-instructions unit)))
        (flet ((change (op before after)
                 (let ((target (find-if (lambda (i) (and (eq op (mognitio.machine:instruction-opcode i))
                                                        (equal before (mognitio.machine:instruction-operands i)))) instructions)))
                   (is target) (setf (mognitio.machine:instruction-operands target) after))))
          (ecase mutation
            (:nofollow (change :mov-r10d '(256) '(0)))
            (:device (change :load-frame '(:rax -320) '(:rax -312)))
            (:inode (change :load-frame '(:rax -312) '(:rax -320)))
            (:roots (change :imm-rax '(4) '(3)))
            (:cleanup (change :call '((:runtime :io.cleanup)) '((:runtime :io.close))))
            (:identity-root (change :store-frame '(-16 :rdx) '(-176 :rdx)))
            (:comparison-word (change :load-word '(:rax :rsi 40) '(:rax :rsi 32))))
          (signals internal-failure (mognitio.native.runtime::verify-io-units units)))))))

(deftest v150-identity-descriptor-proof
  (let* ((ir (mognitio.ir:lower-program (project-checked (v150-manifest "discard inspectPath(\"/\");0")))))
    (multiple-value-bind (bytes symbols) (mognitio.amd64:encode (mognitio.machine:lower-module ir))
      (is (mognitio.backend.native::verify-native-metadata ir bytes symbols))
      (let* ((symbol (gethash '(:layout (:file-identity)) symbols))
             (offset (mognitio.object:image-symbol-offset symbol)))
        (dolist (at '(0 24 32))
          (let ((bad (copy-seq bytes)))
            (incf (aref bad (+ offset at)))
            (signals internal-failure (mognitio.backend.native::verify-native-metadata ir bad symbols))))))))

(deftest v150-native-stat-abi
  (let* ((path (put-text (fresh-path ".data") "identity"))
         (stat (sb-posix:lstat path)))
    (multiple-value-bind (kind identity) (mognitio.io::inspect-path-value (v12-text (namestring path)))
      (same 0 kind)
      (same (sb-posix:stat-dev stat) (mognitio.io::file-identity-device identity))
      (same (sb-posix:stat-ino stat) (mognitio.io::file-identity-inode identity)))))
