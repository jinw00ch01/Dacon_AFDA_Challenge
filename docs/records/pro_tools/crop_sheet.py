import sys, cv2, numpy as np
video, start, end, out = sys.argv[1], int(sys.argv[2]), int(sys.argv[3]), sys.argv[4]
x0, y0, x1, y1 = [int(v) for v in sys.argv[5].split(",")]
cap = cv2.VideoCapture(video)
tiles = []
i = 0
while True:
    ok, f = cap.read()
    if not ok or i >= end: break
    if i >= start:
        c = f[y0:y1, x0:x1].copy()
        s = 300 / c.shape[1]
        c = cv2.resize(c, (300, int(c.shape[0]*s)))
        cv2.putText(c, str(i), (5, 20), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0,255,255), 2)
        tiles.append(c)
    i += 1
cols = 4
while len(tiles) % cols: tiles.append(np.zeros_like(tiles[0]))
rows = [np.hstack(tiles[r:r+cols]) for r in range(0, len(tiles), cols)]
cv2.imwrite(out, np.vstack(rows))
print(out, len(tiles))
