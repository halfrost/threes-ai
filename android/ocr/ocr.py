import PIL.Image as Image
import numpy as np
import os
import re
import glob
from devices import CONFIGS

DNAME = os.path.dirname(__file__)

def to_ind(val):
    return {0:0, 1:1, 2:2, 3:3, 6:4, 12:5, 24:6, 48:7, 96:8, 192:9, 384:10, 768:11, 1536:12, 3072:13, 6144:14}[val]

def to_imgkey(imc):
    return np.asarray(imc).tostring()

class ExemplarMatcher:
    def __init__(self, cfg, dir, tag, thresh=500000):
        self.cfg = cfg
        self.dir = dir
        self.tag = tag
        self.loaded = False
        self.exemplars = {}
        self.lastid = {}
        self.guess_thresh = thresh
        try:
            os.makedirs(self.exemplar_dir)
        except EnvironmentError:
            pass

    @property
    def exemplar_dir(self):
        return os.path.join(DNAME, 'exemplars', self.dir, self.tag)

    def get_exemplars(self):
        d = self.exemplar_dir
        for fn in os.listdir(d):
            m = re.match(r'^(.+)\.(\d+)\.png$', fn)
            if m:
                yield m.group(1), int(m.group(2)), Image.open(os.path.join(d, fn))

    def load(self):
        self.exemplars = {}
        for val, ind, im in self.get_exemplars():
            self.exemplars[to_imgkey(im)] = val
            self.lastid[val] = max(self.lastid.get(val, 0), ind)
        self.loaded = True

    def guess_classify(self, imc):
        possible = set()
        imcarr = np.asarray(imc).astype(float)
        for val, ind, im in self.get_exemplars():
            err = np.asarray(im).astype(float) - imcarr
            if 0 < np.abs(err).sum() < self.guess_thresh:
                possible.add(val)
        if len(possible) == 1:
            return possible.pop()
        elif len(possible) > 1:
            print "Warning: multiple matches %s; guesser may not be accurate!" % possible
        return None

    def classify(self, imc):
        if not self.loaded:
            self.load()

        key = to_imgkey(imc)
        val = self.exemplars.get(key, None)
        if val is not None:
            return val

        val = self.guess_classify(imc)
        if val is not None:
            print "Unrecognized %s automatically classified as %s" % (self.tag, val)
        else:
            imc.show()
            val = raw_input("\aUnrecognized %s! Recognize it and type in the value: " % self.tag)

        nid = self.lastid.get(val, 0) + 1
        imc.save(os.path.join(self.exemplar_dir, '%s.%d.png' % (val, nid)))
        self.exemplars[to_imgkey(imc)] = val
        self.lastid[val] = nid
        return val

def extract_tile(cfg, im, r, c):
    x = cfg.x0 + c*cfg.dx
    y = cfg.y0 + r*cfg.dy

    return im.crop((int(x), int(y), int(x+cfg.w), int(y+cfg.h)))

def extract_next(cfg, im):
    return im.crop((cfg.tx, cfg.ty, cfg.tx + cfg.tw, cfg.ty + cfg.th))

class OCR:
    def __init__(self, model):
        if model not in CONFIGS:
            raise ValueError("Configuration for model %s not found: please add it in devices.py" % model)
        self.cfg = CONFIGS[model]
        self.next_matcher = ExemplarMatcher(self.cfg, model, 'next', 50000)
        self.tile_matcher = ExemplarMatcher(self.cfg, model, 'tile', 500000)

    def ocr(self, fn):
        if isinstance(fn, Image.Image):
            im = fn
        else:
            im = Image.open(fn)
        imc = extract_next(self.cfg, im)
        tileset = self.next_matcher.classify(imc)
        if tileset == 'gameover':
            return None, None
        tileset = [to_ind(int(t)) for t in tileset.split(',')]
        out = np.zeros((4,4), dtype=int)

        for r in xrange(4):
            for c in xrange(4):
                imc = extract_tile(self.cfg, im, r, c)
                out[r,c] = to_ind(int(self.tile_matcher.classify(imc)))

        return out, tileset

if __name__ == '__main__':
    import sys
    if len(sys.argv) < 3:
        print "Usage:", sys.argv[0], "modelname", "files..."
        exit()

    model = sys.argv[1]
    ocr = OCR(model)
    for fn in sys.argv[2:]:
        print fn
        print ocr.ocr(fn)
        print
