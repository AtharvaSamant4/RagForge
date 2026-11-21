"""Create selectable-text PDF and DOCX demo sources; no external services."""
from pathlib import Path
from docx import Document
from reportlab.lib.pagesizes import A4
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet

root = Path(__file__).resolve().parents[1] / "samples"
styles = getSampleStyleSheet()
sections = [
    ("Acme customer handbook", "Title"),
    ("Refund policy", "Heading2"),
    ("Acme offers a 30 day refund period for all annual subscriptions. To request a refund, email support@acme.example with your invoice number. Refunds are returned to the original payment method within seven business days.", "BodyText"),
    ("Support hours", "Heading2"),
    ("Acme support is available Monday through Friday from 09:00 to 18:00 UTC. Customers on the Enterprise plan receive a response within four business hours.", "BodyText"),
    ("Data retention", "Heading2"),
    ("Acme retains uploaded customer documents until the customer deletes them. Deleting a document removes its retrieval index entries. Backups expire after thirty days.", "BodyText"),
]
story = []
word = Document()
for text, style in sections:
    story += [Paragraph(text, styles[style]), Spacer(1, 12)]
    if style == "Title":
        word.add_heading(text, 0)
    elif style == "Heading2":
        word.add_heading(text, 1)
    else:
        word.add_paragraph(text)
SimpleDocTemplate(str(root / "acme-handbook.pdf"), pagesize=A4).build(story)
word.save(root / "acme-handbook.docx")
print("Generated samples/acme-handbook.pdf and samples/acme-handbook.docx")
