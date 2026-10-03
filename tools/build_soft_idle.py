"""生成轻柔呼吸待机与固定揉头姿态，不改动上游动画。

用法：python tools/build_soft_idle.py
需要项目运行依赖 Pillow、imageio-ffmpeg。过程日志默认写入项目旁的
build/records/soft-idle-build；输出写入 anim 与 anim/hd。
"""
import argparse
import json
import math
import re
import subprocess
from pathlib import Path

import imageio_ffmpeg
from PIL import Image, ImageChops, ImageStat


ROOT = Path(__file__).resolve().parent.parent
FPS = 24
IDLE_FRAMES = 120
IDLE_LAST_SOURCE_FRAME = 60
BUMP_SOURCE_FRAME = 36  # 双手抬到脸旁，身体仍保持正面姿态。
CREATE_FLAGS = getattr(subprocess, "CREATE_NO_WINDOW", 0)


def read_source_frames(ffmpeg, path, size, last_index):
    command = [ffmpeg, "-v", "error", "-threads", "2", "-c:v", "libvpx-vp9",
               "-i", str(path), "-frames:v", str(last_index + 1), "-an",
               "-f", "rawvideo", "-pix_fmt", "rgba", "-"]
    process = subprocess.Popen(command, stdout=subprocess.PIPE,
                               stderr=subprocess.DEVNULL, creationflags=CREATE_FLAGS)
    frames = []
    frame_bytes = size[0] * size[1] * 4
    try:
        for _ in range(last_index + 1):
            frame = process.stdout.read(frame_bytes)
            if len(frame) != frame_bytes:
                raise RuntimeError("源动画帧不足或尺寸不符：%s" % path)
            frames.append(frame)
        if process.wait() != 0:
            raise RuntimeError("源动画解码失败：%s" % path)
        return frames
    finally:
        if process.poll() is None:
            process.kill()
        process.wait()
        process.stdout.close()


def encode(ffmpeg, target, size, frames, records):
    temporary = records / (target.parent.name + "-" + target.stem + ".partial.webm")
    log_path = temporary.with_suffix(".encode.log")
    command = [ffmpeg, "-y", "-v", "error", "-f", "rawvideo", "-pix_fmt", "rgba",
               "-s", "%dx%d" % size, "-r", str(FPS), "-i", "-", "-an",
               "-c:v", "libvpx-vp9", "-pix_fmt", "yuva420p", "-lossless", "1",
               "-b:v", "0", "-deadline", "good", "-cpu-used", "4",
               "-row-mt", "1", "-threads", "2", "-auto-alt-ref", "0",
               str(temporary)]
    with log_path.open("wb") as log:
        process = subprocess.Popen(command, stdin=subprocess.PIPE, stderr=log,
                                   creationflags=CREATE_FLAGS)
        try:
            for frame in frames:
                process.stdin.write(frame)
            process.stdin.close()
            if process.wait() != 0:
                raise RuntimeError("动画编码失败，参见：%s" % log_path)
        finally:
            if process.poll() is None:
                process.kill()
            process.wait()
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary.replace(target)


def verify(ffmpeg, target, size, expected_frames, source_first):
    metadata = subprocess.run([ffmpeg, "-hide_banner", "-i", str(target)],
                              capture_output=True, creationflags=CREATE_FLAGS)
    info = metadata.stderr.decode("utf-8", errors="replace")
    if not re.search(r"\b%d[x]%d\b" % size, info) or "24 fps" not in info:
        raise RuntimeError("输出尺寸或帧率不符：%s" % target)
    decoded = read_source_frames(ffmpeg, target, size, expected_frames - 1)
    first = Image.frombytes("RGBA", size, decoded[0])
    last = Image.frombytes("RGBA", size, decoded[-1])
    alpha = first.getchannel("A")
    source_alpha = Image.frombytes("RGBA", size, source_first).getchannel("A")
    if alpha.getextrema() != (0, 255):
        raise RuntimeError("输出缺失透明通道：%s" % target)
    alpha_difference = ImageChops.difference(alpha, source_alpha)
    # RGBA -> yuva420p 的范围换算在半透明边缘会有 1/255 的舍入误差。
    if alpha_difference.getextrema()[1] > 1:
        raise RuntimeError("无损编码没有保留源透明通道：%s" % target)
    differences = []
    for before, after in zip(decoded, decoded[1:]):
        a, b = Image.frombytes("RGBA", size, before), Image.frombytes("RGBA", size, after)
        differences.append(sum(ImageStat.Stat(ImageChops.difference(a, b)).mean) / 4)
    seam = sum(ImageStat.Stat(ImageChops.difference(first, last)).mean) / 4
    if seam != 0:
        raise RuntimeError("循环首尾未衔接：%s" % target)
    bbox = alpha.point(lambda value: 255 if value > 12 else 0).getbbox()
    return dict(path=str(target.relative_to(ROOT)), bytes=target.stat().st_size,
                width=size[0], height=size[1], fps=FPS, frames=expected_frames,
                alpha_range=alpha.getextrema(),
                source_alpha_max_error=alpha_difference.getextrema()[1],
                reference_bbox=bbox,
                normalized_bbox=[bbox[0]/size[0], bbox[1]/size[1],
                                 bbox[2]/size[0], bbox[3]/size[1]],
                seam_rgba_mae=seam,
                adjacent_rgba_mae_max=max(differences, default=0),
                adjacent_rgba_mae_mean=sum(differences) / max(1, len(differences)))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--records", type=Path,
                        default=ROOT.parent / "build/records" / "soft-idle-build")
    args = parser.parse_args()
    args.records.mkdir(parents=True, exist_ok=True)
    ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
    # 一周期内从 0 缓缓到 60，再缓缓返回 0；两端余弦导数为零。
    indices = [round(IDLE_LAST_SOURCE_FRAME *
                     (1 - math.cos(2 * math.pi * index / IDLE_FRAMES)) / 2)
               for index in range(IDLE_FRAMES)]
    results = []
    for folder, size in [(ROOT / "anim", (640, 360)),
                         (ROOT / "anim" / "hd", (1280, 720))]:
        idle = read_source_frames(ffmpeg, folder / "待机呼吸休闲.webm", size,
                                  IDLE_LAST_SOURCE_FRAME)
        target = folder / "待机轻柔呼吸.webm"
        encode(ffmpeg, target, size, (idle[index] for index in indices), args.records)
        results.append(verify(ffmpeg, target, size, IDLE_FRAMES, idle[0]))
        del idle
        bump = read_source_frames(ffmpeg, folder / "点击回应-害羞惊讶.webm", size,
                                  BUMP_SOURCE_FRAME)[BUMP_SOURCE_FRAME]
        target = folder / "碰撞揉头轻颤.webm"
        encode(ffmpeg, target, size, (bump for _ in range(FPS)), args.records)
        results.append(verify(ffmpeg, target, size, FPS, bump))
        print(json.dumps(results[-2:], ensure_ascii=False), flush=True)
    report = dict(idle_source="待机呼吸休闲", idle_indices=indices,
                  bump_source="点击回应-害羞惊讶", bump_source_frame=BUMP_SOURCE_FRAME,
                  outputs=results)
    (args.records / "verification.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
