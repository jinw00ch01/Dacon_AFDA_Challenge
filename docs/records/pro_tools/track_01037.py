import cv2, numpy as np
cap=cv2.VideoCapture('data/external/nexar_subset_v1/train/positive/01037.mp4')
i=0
while True:
    ok,f=cap.read()
    if not ok or i>700: break
    if i>=600 and i%1==0:
        s=cv2.resize(f,(640,360))
        hsv=cv2.cvtColor(s,cv2.COLOR_BGR2HSV)
        roi=hsv[180:350,30:360]
        red=((roi[...,0]<8)|(roi[...,0]>170))&(roi[...,1]>120)&(roi[...,2]>150)
        ys,xs=np.nonzero(red)
        g=cv2.cvtColor(s,cv2.COLOR_BGR2GRAY)[180:350,30:360]
        # car roof edge: row of strongest horizontal gradient in center column band
        if len(xs): print(i,len(xs),round(xs.mean()+30,1),round(ys.mean()+180,1),round(xs.min()+30),round(xs.max()+30))
    i+=1
