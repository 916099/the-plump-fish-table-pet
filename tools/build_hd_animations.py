"""从上游 720p 源视频恢复颜色细节，复用现有人工抠像的透明通道。

原素材保留；高清版本输出到 anim/hd。需要 numpy、opencv-python、imageio-ffmpeg。
用法：python tools/build_hd_animations.py --sources SOURCE_DIR --output anim/hd --records RECORD_DIR
"""
import argparse,json,subprocess,concurrent.futures,time
from pathlib import Path
import cv2,numpy as np,imageio_ffmpeg

ROOT=Path(__file__).resolve().parent.parent
FFMPEG=imageio_ffmpeg.get_ffmpeg_exe()
cv2.setNumThreads(1)

def reader(path,alpha):
    cmd=[FFMPEG,'-v','error','-threads','1']+(['-c:v','libvpx-vp9'] if alpha else [])
    cmd+=['-i',str(path),'-an','-f','rawvideo','-pix_fmt','rgba' if alpha else 'rgb24','-']
    return subprocess.Popen(cmd,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL)

def read_frame(proc,w,h,channels):
    count=w*h*channels
    data=proc.stdout.read(count)
    return np.frombuffer(data,np.uint8).reshape(h,w,channels) if len(data)==count else None

def align(source,old):
    orb=cv2.ORB_create(nfeatures=4000,fastThreshold=6)
    ks,ds=orb.detectAndCompute(cv2.cvtColor(source,cv2.COLOR_RGB2GRAY),None)
    ko,do=orb.detectAndCompute(cv2.cvtColor(old[:,:,:3],cv2.COLOR_RGB2GRAY),(old[:,:,3]>200).astype(np.uint8)*255)
    if ds is None or do is None:raise ValueError('无可用的角色匹配点')
    good=[a for a,b in cv2.BFMatcher(cv2.NORM_HAMMING).knnMatch(ds,do,k=2) if a.distance<.75*b.distance]
    if len(good)<12:raise ValueError('角色匹配点不足')
    matrix,inliers=cv2.estimateAffinePartial2D(np.float32([ks[a.queryIdx].pt for a in good]),
        np.float32([ko[a.trainIdx].pt for a in good]),method=cv2.RANSAC,ransacReprojThreshold=1.5)
    if matrix is None or int(inliers.sum())<12:raise ValueError('角色对齐未通过')
    return matrix,int(inliers.sum())

def build(name,sources,output,records):
    old_proc=reader(ROOT/'anim'/(name+'.webm'),True)
    src_proc=reader(sources/(name+'.mp4'),False)
    encoder=None;temporary=records/(name+'.partial.webm')
    try:
        old=read_frame(old_proc,640,360,4);source=read_frame(src_proc,1280,720,3)
        if old is None or source is None:raise ValueError('无法读取首帧')
        matrix,inliers=align(source,old)
        cmd=[FFMPEG,'-y','-v','error','-f','rawvideo','-pix_fmt','rgba','-s','1280x720','-r','24','-i','-',
             '-an','-c:v','libvpx-vp9','-pix_fmt','yuva420p','-b:v','0','-crf','18',
             '-deadline','realtime','-cpu-used','8','-row-mt','1','-threads','2','-auto-alt-ref','0',str(temporary)]
        log=(records/(name+'.encode.log')).open('wb')
        encoder=subprocess.Popen(cmd,stdin=subprocess.PIPE,stderr=log)
        frames=0;errors=[]
        while old is not None and source is not None:
            ys,xs=np.where(old[:,:,3]>4)
            x0,y0=max(0,int(xs.min())-2),max(0,int(ys.min())-2)
            x1,y1=min(640,int(xs.max())+3),min(360,int(ys.max())+3)
            roi_matrix=matrix*2;roi_matrix[:,2]-=(x0*2,y0*2)
            rgb=cv2.warpAffine(source,roi_matrix,((x1-x0)*2,(y1-y0)*2),flags=cv2.INTER_LANCZOS4,borderMode=cv2.BORDER_CONSTANT)
            alpha=cv2.resize(old[y0:y1,x0:x1,3],((x1-x0)*2,(y1-y0)*2),interpolation=cv2.INTER_LINEAR)
            alpha[alpha<=4]=0
            # 原人工抠像颜色只用于修补绿幕边缘，保留真实的绿色道具。
            reference=cv2.resize(old[y0:y1,x0:x1,:3],((x1-x0)*2,(y1-y0)*2),interpolation=cv2.INTER_CUBIC)
            edge=(alpha>0)&(rgb[:,:,1]>np.maximum(rgb[:,:,0],rgb[:,:,2])*1.05)&(reference[:,:,1]<=np.maximum(reference[:,:,0],reference[:,:,2])*1.03)
            rgb[edge]=reference[edge]
            rgb[alpha==0]=0
            rgba=np.zeros((720,1280,4),np.uint8)
            rgba[y0*2:y1*2,x0*2:x1*2]=np.dstack((rgb,alpha))
            if frames in (0,60,120,180):
                reduced=cv2.resize(rgba[:,:,:3],(640,360),interpolation=cv2.INTER_AREA)
                opaque=old[:,:,3]>240
                if np.any(opaque):errors.append(float(np.median(np.abs(reduced.astype(np.int16)-old[:,:,:3].astype(np.int16))[opaque])))
                if frames==0:
                    cv2.imencode('.png',cv2.cvtColor(rgba,cv2.COLOR_RGBA2BGRA))[1].tofile(str(records/(name+'.hd.png')))
            encoder.stdin.write(rgba.tobytes());frames+=1
            old=read_frame(old_proc,640,360,4);source=read_frame(src_proc,1280,720,3)
        encoder.stdin.close();code=encoder.wait();log.close()
        if code or frames<24 or old is not None or max(errors,default=255)>28:
            raise ValueError(f'输出校验失败: code={code}, frames={frames}, rgb_median={errors}')
        temporary.replace(output/(name+'.webm'))
        result=dict(name=name,frames=frames,width=1280,height=720,fps=24,inliers=inliers,transform=matrix.tolist(),rgb_median_errors=errors)
        (records/(name+'.json')).write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf8')
        return result
    finally:
        for p in (old_proc,src_proc,encoder):
            if p is not None:
                if p.poll() is None:p.kill()
                p.wait()

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--sources',type=Path,required=True)
    parser.add_argument('--output',type=Path,default=ROOT/'anim'/'hd');parser.add_argument('--records',type=Path,required=True)
    parser.add_argument('--only',default='');parser.add_argument('--workers',type=int,default=3)
    args=parser.parse_args();args.output.mkdir(parents=True,exist_ok=True);args.records.mkdir(parents=True,exist_ok=True)
    names=[p.stem for p in (ROOT/'anim').glob('*.webm') if (args.sources/(p.stem+'.mp4')).exists()
           and (not args.only or p.stem==args.only) and not (args.output/p.name).exists()]
    failed=[];start=time.perf_counter()
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures={pool.submit(build,n,args.sources,args.output,args.records):n for n in names}
        for i,future in enumerate(concurrent.futures.as_completed(futures),1):
            try:r=future.result();print(f'{i}/{len(names)} OK {r["name"]} frames={r["frames"]}',flush=True)
            except Exception as e:failed.append(futures[future]);print(f'{i}/{len(names)} FAIL {futures[future]} {e}',flush=True)
    print(json.dumps(dict(seconds=round(time.perf_counter()-start),failed=failed),ensure_ascii=False),flush=True)
    return bool(failed)
if __name__=='__main__':raise SystemExit(main())
