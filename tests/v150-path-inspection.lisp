(in-package #:mognitio.tests)

(defparameter *v150-imports*
  "use Std\\Io\\{inspectPath,FileIdentity,PathInfo,PathInfoError,DirectoryEntryKind,IoErrorKind};")
(defun v150-manifest (body &optional (extra ""))
  (project-fixture (list (cons "app.mgn"
    (format nil "namespace App;~A~Alet main:Function(List<String>):Int=function(args:List<String>):Int{~A};"
            *v150-imports* extra body)))))
(defun v150-info (path)
  (format nil "branch on inspectPath(~S){Result<PathInfo,PathInfoError>::Ok(observed:PathInfo)=>observed,Result<PathInfo,PathInfoError>::Err(e:PathInfoError)=>panic{e->subject}}" path))
(defun v150-kind (path kind)
  (format nil "let info:PathInfo=~A;assert branch on info->kind{~{~A~^,~}};0"
    (v150-info path)
    (loop for name in '("File" "Directory" "Symlink" "Other")
          collect (format nil "DirectoryEntryKind::~A=>~A" name (if (equal name kind) "true" "false")))))
(defun v150-error (path kind)
  (format nil "branch on inspectPath(~S){Result<PathInfo,PathInfoError>::Ok=>1,Result<PathInfo,PathInfoError>::Err(e:PathInfoError)=>{assert e->subject==~S;branch on e->kind{~A}}}"
          path path (v13-kind-arms kind)))
(defun v150-both (body &optional (extra "") options)
  (let ((manifest (v150-manifest body extra))) (expect-project manifest options)))

(deftest v150-observation-and-identity
  (let* ((root (v13-directory)) (file (concatenate 'string root "/file"))
         (hard (concatenate 'string root "/hard")) (other (concatenate 'string root "/other"))
         (link (concatenate 'string root "/link")) (dangling (concatenate 'string root "/dangling"))
         (pipe (concatenate 'string root "/pipe")))
    (put-text (pathname file) "same") (put-text (pathname other) "same")
    (sb-posix:link file hard) (sb-posix:symlink root link) (sb-posix:symlink "missing" dangling)
    (sb-posix:mkfifo pipe #o600)
    (dolist (case (list (list file "File") (list root "Directory") (list pipe "Other")
                       (list link "Symlink") (list (concatenate 'string link "///") "Symlink")
                       (list (concatenate 'string link "/.") "Directory") (list dangling "Symlink")
                       (list (concatenate 'string dangling "/") "Symlink") (list "////" "Directory")))
      (v150-both (v150-kind (first case) (second case))))
    (dolist (case (list (list "" "InvalidPath") (list (concatenate 'string root "/missing") "NotFound")
                       (list (concatenate 'string file "/child") "UnsupportedTarget")
                       (list (concatenate 'string dangling "/child") "NotFound")))
      (v150-both (v150-error (first case) (second case))))
    (v150-both (format nil "let link:PathInfo=~A;let slash:PathInfo=~A;let target:PathInfo=~A;
      assert link->identity==slash->identity;assert link->identity!=target->identity;0"
      (v150-info link) (v150-info (concatenate 'string link "///")) (v150-info root)))
    (v150-both (format nil "let a:PathInfo=~A;let b:PathInfo=~A;let c:PathInfo=~A;let d:PathInfo=~A;
      assert a->identity==a->identity;assert a->identity==b->identity;assert b->identity==a->identity;
      assert a->identity==c->identity;assert a->identity!=d->identity;0"
      (v150-info file) (v150-info hard) (v150-info file) (v150-info other)))))

(deftest v150-storage-first-class-and-gc
  (let ((root (v13-directory)))
    (v150-both (format nil "let api:Function(String):Result<PathInfo,PathInfoError>=inspectPath;
      let saved:Function(String):Result<PathInfo,PathInfoError>=function(p:String):Result<PathInfo,PathInfoError>{api(p)};
      let info:PathInfo=~A;let identity:FileIdentity=info->identity;
      let boxed:Box<FileIdentity>=Box<FileIdentity>{value:identity};
      let carried:Carry=Carry::Ready(identity);
      let kept:Result<Token,PathInfoError>=Result<Token,PathInfoError>::Ok(identity);
      let capture:Function():FileIdentity=function():FileIdentity{boxed->value};
      var i:Int=0;loop while(i<80){
        let values:List<FileIdentity>=List<FileIdentity>[capture(),identity];
        loop over(values as v:FileIdentity){assert v==identity;};
        assert branch on saved(~S){Result<PathInfo,PathInfoError>::Ok(x:PathInfo)=>x->identity==identity,Result<PathInfo,PathInfoError>::Err=>false};
        let synthetic:PathInfo=PathInfo{kind:DirectoryEntryKind::Other,identity:capture()};
        assert synthetic->identity==identity;
        assert branch on carried{Carry::Ready(v:Token)=>v==identity};
        assert branch on kept{Result<Token,PathInfoError>::Ok(v:Token)=>v==identity,Result<Token,PathInfoError>::Err=>false};
        i=i+1;};0" (v150-info root) root)
      "type Box<T>=product{value:T;};alias Token=FileIdentity;type Carry=sum{Ready(Token);};" '(:stress t :validate t :arena-unit 4096 :cap 65536))))

(deftest v150-host-unit-literal
  (v150-both "let checked:Unit={assert true;};assert checked==unit;0"))
