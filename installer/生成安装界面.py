from PIL import Image, ImageDraw, ImageFont
from pathlib import Path
import os
root=Path(__file__).resolve().parent.parent
out=root/'installer'; out.mkdir(exist_ok=True)
w,h=492,942
im=Image.new('RGB',(w,h)); px=im.load()
for y in range(h):
 t=y/(h-1)
 for x in range(w):
  px[x,y]=(int(25+26*t),int(39+23*t),int(87+34*t))
d=ImageDraw.Draw(im)
for x,y,r in [(37,57,2),(430,98,2),(70,378,3),(407,320,2),(385,755,3),(85,698,2),(213,190,2)]: d.ellipse((x-r,y-r,x+r,y+r),fill=(193,216,255))
d.ellipse((337,25,434,122),outline=(116,155,213),width=2)
d.ellipse((350,38,421,109),outline=(83,121,181),width=2)
font=str(Path(os.environ.get('WINDIR', 'C:/Windows'))/'Fonts'/'msyh.ttc')
large=ImageFont.truetype(font,43); small=ImageFont.truetype(font,23); en=ImageFont.truetype(font,18)
d.text((37,61),'大肥鱼桌宠',font=large,fill=(247,248,255))
d.text((40,124),'让小鱼住进你的桌面',font=small,fill=(195,215,246))
d.line((40,168,450,168),fill=(117,156,212),width=2)
sprite=Image.open(root/'sprites'/'正面.png').convert('RGBA'); sprite.thumbnail((390,520),Image.Resampling.LANCZOS)
im.paste(sprite,((w-sprite.width)//2,230),sprite)
d=ImageDraw.Draw(im); d.rounded_rectangle((39,814,453,885),18,outline=(112,151,208),width=2,fill=(30,50,101))
d.text((71,834),'透明桌宠  ·  随时陪伴',font=small,fill=(227,237,255))
im.save(out/'wizard.bmp')
smallim=Image.new('RGB',(165,165),(244,248,255)); sp=Image.open(root/'sprites'/'正面.png').convert('RGBA'); sp.thumbnail((135,150),Image.Resampling.LANCZOS);smallim.paste(sp,((165-sp.width)//2,(165-sp.height)//2),sp);smallim.save(out/'wizard-small.bmp')
