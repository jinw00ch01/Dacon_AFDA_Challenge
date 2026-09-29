import cv2, numpy as np
cap=cv2.VideoCapture('data/external/nexar_subset_v1/train/positive/01037.mp4')
prev=None;i=0
while True:
    ok,f=cap.read()
    if not ok or i>660: break
    if i>=596:
        g=cv2.cvtColor(cv2.resize(f,(640,360)),cv2.COLOR_BGR2GRAY).astype(np.float32)
        top=g[:150,:]
        if prev is not None:
            (dx,dy),r=cv2.phaseCorrelate(prev,top)
            # car region size: bright pixel count in lower center
            low=g[200:340,40:300]
            print(i,round(dx,2),round(dy,2),round(r,2),int((low>200).sum()))
        prev=top
    i+=1
