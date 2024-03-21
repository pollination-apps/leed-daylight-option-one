from reportlab.pdfgen import canvas
from reportlab.platypus import BaseDocTemplate, Paragraph
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.lib.units import mm


class MyDocTemplate(BaseDocTemplate):

    def __init__(self, filename, **kw):
        self.allowSplitting = 0
        self.skip_pages = kw.pop('skip_pages', 0)
        self.start_on_skip_pages = kw.pop('start_on_skip_pages', None)
        BaseDocTemplate.__init__(self, filename, **kw)

    def afterFlowable(self, flowable):
        "Registers TOC entries."
        if isinstance(flowable, Paragraph):
            text = flowable.getPlainText()
            style = flowable.style.name
            pageNum = self.page - self.skip_pages
            if style == 'Heading1':
                key = 'h1-%s' % self.seq.nextf('Heading1')
                self.canv.bookmarkPage(key)
                self.notify('TOCEntry', (0, text, pageNum))
            if style == 'Heading2':
                key = 'h2-%s' % self.seq.nextf('heading2')
                self.canv.bookmarkPage(key)
                self.notify('TOCEntry', (1, text, pageNum))


class NumberedPageCanvas(canvas.Canvas):
    """
    http://code.activestate.com/recipes/546511-page-x-of-y-with-reportlab/
    http://code.activestate.com/recipes/576832/
    http://www.blog.pythonlibrary.org/2013/08/12/reportlab-how-to-add-page-numbers/
    https://stackoverflow.com/a/59882495/
    """

    def __init__(self, *args, **kwargs):
        """Constructor."""
        self.skip_pages = kwargs.pop('skip_pages', 0)
        self.start_on_skip_pages = kwargs.pop('start_on_skip_pages', None)
        super().__init__(*args, **kwargs)
        self.pages = []

    def showPage(self):
        """On a page break, add information to the list."""
        self.pages.append(dict(self.__dict__))
        self._doc.pageCounter += 1
        self._startPage()

    def save(self):
        """Add the page number to each page (page x of y)."""
        page_count = len(self.pages)

        for page in self.pages:
            self.__dict__.update(page)
            self.draw_page_number(page_count)
            super().showPage()

        super().save()

    def draw_page_number(self, page_count):
        """Add the page number."""
        if self._pageNumber > self.skip_pages:
            if self.start_on_skip_pages:
                page = "Page %s of %s" % (self._pageNumber - self.skip_pages, page_count - self.skip_pages)
                self.setFont("Helvetica", 9)
                self.drawRightString(195 * mm, 15 * mm, page)
            else:
                page = "Page %s of %s" % (self._pageNumber, page_count)
                self.setFont("Helvetica", 9)
                self.drawRightString(195 * mm, 15 * mm, page)


def _header(canvas, doc, content, logo: None):
    canvas.saveState()
    w, h = content.wrap(doc.width, doc.topMargin)
    content_width = \
        stringWidth(content.text, fontName=content.style.fontName, fontSize=content.style.fontSize)
    content.drawOn(
        canvas,
        doc.leftMargin+doc.width-content_width,
        doc.bottomMargin+doc.height+doc.topMargin-15*mm+1*mm
    )
    if logo:
        canvas.drawImage(
            logo, x=doc.leftMargin,
            y=doc.bottomMargin+doc.height+doc.topMargin-15*mm+1*mm,
            height=5*mm,
            preserveAspectRatio=True,
            anchor='w',
            mask='auto'
        )
    canvas.setLineWidth(0.2)
    canvas.line(
        doc.leftMargin,
        doc.bottomMargin + doc.height + doc.topMargin - 15 * mm,
        doc.leftMargin + doc.width,
        doc.bottomMargin + doc.height + doc.topMargin - 15 * mm)
    canvas.restoreState()


def _footer(canvas, doc, content):
    canvas.saveState()
    w, h = content.wrap(doc.width, doc.bottomMargin)
    content.drawOn(canvas, doc.leftMargin, 15 * mm)
    canvas.restoreState()


def _header_and_footer(canvas, doc, header_content, footer_content, logo):
    _header(canvas, doc, header_content, logo)
    _footer(canvas, doc, footer_content)
