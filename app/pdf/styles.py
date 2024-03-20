from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle, \
    _baseFontName, _baseFontNameB
from reportlab.lib.colors import black, blue, lightblue
from reportlab.lib.enums import TA_CENTER, TA_RIGHT


STYLES = getSampleStyleSheet()
STYLES['BodyText'].leading = 18
STYLES.add(ParagraphStyle(name='Normal_BOLD',
                          parent=STYLES['Normal'],
                          fontSize=10,
                          leading=12,
                          fontName=_baseFontNameB)
)
STYLES.add(ParagraphStyle(name='Normal_CENTER',
                          parent=STYLES['Normal'],
                          alignment=TA_CENTER,
                          fontSize=10,
                          leading=12)
)
STYLES.add(ParagraphStyle(name='Normal_RIGHT',
                          parent=STYLES['Normal'],
                          alignment=TA_RIGHT,
                          fontSize=10,
                          leading=12)
)
STYLES.add(ParagraphStyle(name='Heading1_CENTER',
                          parent=STYLES['Heading1'],
                          alignment=TA_CENTER),
           alias='h1_c'
)
STYLES.add(ParagraphStyle(name='Heading2_CENTER',
                          parent=STYLES['Heading2'],
                          alignment=TA_CENTER),
           alias='h2_c'
)
STYLES.add(ParagraphStyle(name='Normal_URL',
                          fontName=_baseFontName,
                          fontSize=10,
                          leading=12,
                          textColor=blue,
                          underlineColor=blue,
                          underlineWidth=0.5)
)
