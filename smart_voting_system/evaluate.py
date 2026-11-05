"""Measure recognition accuracy on a labelled image folder.

Folder layout:
    dataset/
        person_1/  img1.jpg img2.jpg ...
        person_2/  ...

Usage:
    python evaluate.py dataset --train 3 --tolerance 0.5

For every person the first N images are "registered" and the remaining images
are used as test probes. Reports accuracy, FAR and FRR (the metrics slide 14
of the presentation calls "Training and Testing").
"""
import argparse
import os

import face_recognition
import numpy as np

EXTS = (".jpg", ".jpeg", ".png")


def encode(path):
    img = face_recognition.load_image_file(path)
    encs = face_recognition.face_encodings(img)
    return encs[0] if len(encs) == 1 else None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("dataset")
    ap.add_argument("--train", type=int, default=3)
    ap.add_argument("--tolerance", type=float, default=0.5)
    args = ap.parse_args()

    gallery, probes = {}, []
    for person in sorted(os.listdir(args.dataset)):
        folder = os.path.join(args.dataset, person)
        if not os.path.isdir(folder):
            continue
        files = sorted(f for f in os.listdir(folder) if f.lower().endswith(EXTS))
        encs = [(f, encode(os.path.join(folder, f))) for f in files]
        encs = [e for _, e in encs if e is not None]
        if len(encs) <= args.train:
            print(f"skip {person}: needs more than {args.train} usable images")
            continue
        gallery[person] = encs[:args.train]
        probes += [(person, e) for e in encs[args.train:]]

    names = list(gallery)
    correct = false_accept = false_reject = 0
    # Genuine probes
    for person, enc in probes:
        dists = {n: float(np.min(face_recognition.face_distance(gallery[n], enc)))
                 for n in names}
        best = min(dists, key=dists.get)
        if dists[best] > args.tolerance:
            false_reject += 1
        elif best == person:
            correct += 1
        else:
            false_accept += 1

    total = len(probes)
    if total == 0:
        print("No probe images available.")
        return
    print(f"People enrolled : {len(names)}")
    print(f"Probe images    : {total}")
    print(f"Accuracy        : {correct / total * 100:.2f}%")
    print(f"FAR (wrong ID)  : {false_accept / total * 100:.2f}%")
    print(f"FRR (rejected)  : {false_reject / total * 100:.2f}%")


if __name__ == "__main__":
    main()
