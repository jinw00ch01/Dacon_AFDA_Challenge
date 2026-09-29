"""Check cv2.phaseCorrelate sign: move image content RIGHT by 7 px and print the returned dx."""
import cv2
import numpy as np

rng = np.random.default_rng(0)
a = cv2.GaussianBlur(rng.random((120, 200)).astype(np.float32), (7, 7), 2)
b = np.zeros_like(a)
b[:, 7:] = a[:, :-7]  # content of b = content of a moved 7 px to the RIGHT
(dx, dy), resp = cv2.phaseCorrelate(a, b)
print(f"content moved right by 7 -> phaseCorrelate(a, b) dx={dx:+.2f} dy={dy:+.2f} resp={resp:.2f}")
