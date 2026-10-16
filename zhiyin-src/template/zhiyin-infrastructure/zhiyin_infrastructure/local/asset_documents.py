"""生成真实 PDF / DOCX 字节；正文仅来自持久资产。"""

from io import BytesIO
from xml.sax.saxutils import escape
from zipfile import ZipFile, ZIP_DEFLATED


def render_asset_document(title, lines, fmt):
    if fmt == "docx":
        paragraphs = "".join(
            f'<w:p><w:r><w:t xml:space="preserve">{escape(str(line))}</w:t></w:r></w:p>'
            for line in [title, *lines]
        )
        document = f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?><w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body>{paragraphs}<w:sectPr><w:pgSz w:w="11906" w:h="16838"/><w:pgMar w:top="1440" w:right="1440" w:bottom="1440" w:left="1440"/></w:sectPr></w:body></w:document>'
        output = BytesIO()
        with ZipFile(output, "w", ZIP_DEFLATED) as z:
            z.writestr(
                "[Content_Types].xml",
                '<?xml version="1.0" encoding="UTF-8"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/></Types>',
            )
            z.writestr(
                "_rels/.rels",
                '<?xml version="1.0" encoding="UTF-8"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/></Relationships>',
            )
            z.writestr("word/document.xml", document)
        return output.getvalue()
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.cidfonts import UnicodeCIDFont
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer

    pdfmetrics.registerFont(UnicodeCIDFont("STSong-Light"))
    output = BytesIO()
    style = ParagraphStyle(
        "body", fontName="STSong-Light", fontSize=10, leading=17, wordWrap="CJK", spaceAfter=8
    )
    heading = ParagraphStyle("heading", parent=style, fontSize=18, leading=25)
    story = [Paragraph(escape(title), heading), Spacer(1, 16)]
    story.extend(Paragraph(escape(str(line)).replace("\n", "<br/>"), style) for line in lines)
    SimpleDocTemplate(output, title=title, author="职引", topMargin=48, bottomMargin=48).build(
        story
    )
    return output.getvalue()
