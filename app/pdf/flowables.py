from pdfrw import PdfReader
from pdfrw.buildxobj import pagexobj
from pdfrw.toreportlab import makerl

from reportlab.lib.enums import TA_LEFT, TA_CENTER, TA_RIGHT
from reportlab.platypus import Flowable


class PdfImage(Flowable):
    """
    PdfImage wraps the first page from a PDF file as a Flowable
    which can be included into a ReportLab Platypus document.
    Based on the vectorpdf extension in rst2pdf (http://code.google.com/p/rst2pdf/)

    This can be used from the place where you want to return your matplotlib image
    as a Flowable:

        img = BytesIO()

        fig, ax = plt.subplots(figsize=(canvaswidth,canvaswidth))

        ax.plot([1,2,3],[6,5,4],antialiased=True,linewidth=2,color='red',label='a curve')

        fig.savefig(img,format='PDF')

        return(PdfImage(img))

    """

    def __init__(self, filename_or_object, width=None, height=None, kind='direct', keep_ratio=True):
        if hasattr(filename_or_object, 'read'):
            filename_or_object.seek(0)
        self.page = PdfReader(filename_or_object, decompress=False).pages[0]
        self.xobj = pagexobj(self.page)
        self.imageWidth = width
        self.imageHeight = height
        x1, y1, x2, y2 = self.xobj.BBox

        self._w, self._h = x2 - x1, y2 - y1
        if keep_ratio:
            ratio = self._w / self._h
            if not self.imageWidth:
                self.imageWidth = height * ratio
            elif not self.imageHeight:
                self.imageHeight = width / ratio
            else:
                raise ValueError('Either width or height must be specified.')
        else:
            if not self.imageWidth:
                self.imageWidth = self._w
            if not self.imageHeight:
                self.imageHeight = self._h
        self._ratio = float(self.imageWidth) / self.imageHeight
        if kind in ['direct','absolute'] or width==None or height==None:
            self.drawWidth = width or self.imageWidth
            self.drawHeight = height or self.imageHeight
        elif kind in ['bound','proportional']:
            factor = min(float(width)/self._w,float(height)/self._h)
            self.drawWidth = self._w*factor
            self.drawHeight = self._h*factor

    def wrap(self, availableWidth, availableHeight):
        """
        returns draw- width and height

        convenience function to adapt your image 
        to the available Space that is available
        """
        return self.drawWidth, self.drawHeight

    def drawOn(self, canv, x, y, _sW=0):
        """
        translates Bounding Box and scales the given canvas
        """
        x = 0 # override to avoid margins of frame
        y = 0 # override to avoid margins of frame
        if _sW > 0 and hasattr(self, 'hAlign'):
            a = self.hAlign
            if a in ('CENTER', 'CENTRE', TA_CENTER):
                x += 0.5*_sW
            elif a in ('RIGHT', TA_RIGHT):
                x += _sW
            elif a not in ('LEFT', TA_LEFT):
                raise ValueError("Bad hAlign value " + str(a))

        xobj_name = makerl(canv, self.xobj)

        xscale = self.drawWidth/self._w
        yscale = self.drawHeight/self._h

        x -= self.xobj.BBox[0] * xscale
        y -= self.xobj.BBox[1] * yscale

        canv.saveState()
        canv.translate(x, y)
        canv.scale(xscale, yscale)
        canv.doForm(xobj_name)
        canv.restoreState()
