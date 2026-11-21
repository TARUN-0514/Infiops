import io

from httpx import AsyncClient

from app.ai import parsers
from app.ai.providers import ScriptedProvider
from tests.conftest import auth_headers

API = "/api/v1"


def _docx() -> bytes:
    import docx

    d = docx.Document()
    d.add_paragraph("Incident response runbook.")
    d.add_paragraph("Rotate the API keys within 24 hours of a confirmed breach.")
    t = d.add_table(rows=1, cols=2)
    t.rows[0].cells[0].text, t.rows[0].cells[1].text = "Owner", "SecOps"
    buf = io.BytesIO()
    d.save(buf)
    return buf.getvalue()


def _xlsx() -> bytes:
    from openpyxl import Workbook

    wb = Workbook()
    ws = wb.active
    ws.title = "Vulns"
    ws.append(["CVE", "Severity"])
    ws.append(["CVE-2026-1234", "Critical"])
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def _pptx() -> bytes:
    from pptx import Presentation

    p = Presentation()
    s = p.slides.add_slide(p.slide_layouts[1])
    s.shapes.title.text = "Roadmap"
    s.placeholders[1].text = "Ship the knowledge base in phase 2"
    buf = io.BytesIO()
    p.save(buf)
    return buf.getvalue()


def _pdf(text: str) -> bytes:
    """A one-page PDF with real text, built by hand."""
    stream = f"BT /F1 12 Tf 72 720 Td ({text}) Tj ET".encode()
    objs = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R "
        b"/Resources << /Font << /F1 5 0 R >> >> >>",
        b"<< /Length %d >>\nstream\n" % len(stream) + stream + b"\nendstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    out, offsets = b"%PDF-1.4\n", []
    for i, body in enumerate(objs, 1):
        offsets.append(len(out))
        out += b"%d 0 obj\n" % i + body + b"\nendobj\n"
    xref = len(out)
    out += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objs) + 1)
    out += b"".join(b"%010d 00000 n \n" % o for o in offsets)
    out += b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF" % (len(objs) + 1, xref)
    return out


def test_parsers_extract_text_with_locations() -> None:
    assert "Rotate the API keys" in parsers.parse(_docx(), parsers.DOCX)[0].text
    sheet = parsers.parse(_xlsx(), parsers.XLSX)[0]
    assert sheet.label == "Vulns" and "CVE-2026-1234 | Critical" in sheet.text
    slide = parsers.parse(_pptx(), parsers.PPTX)[0]
    assert slide.page == 1 and "knowledge base" in slide.text
    page = parsers.parse(_pdf("Quarterly revenue grew 12 percent"), parsers.PDF)[0]
    assert page.page == 1 and "revenue grew" in page.text
    vtt = b"WEBVTT\n\n00:00:01.000 --> 00:00:04.000\nWelcome to the standup.\n"
    assert parsers.parse(vtt, "text/vtt")[0].text == "Welcome to the standup."
    chunks = parsers.chunk([parsers.Section("A sentence. " * 300, page=3)], size=500, overlap=50)
    assert len(chunks) > 5 and all(len(c.text) <= 500 for c in chunks) and chunks[0].page == 3


def test_type_detection_trusts_bytes() -> None:
    assert parsers.detect_type("x.txt", b"%PDF-1.4", "text/plain") == parsers.PDF
    try:
        parsers.detect_type("evil.docx", b"MZ\x90\x00", None)
    except parsers.ParseError:
        pass
    else:
        raise AssertionError("an .exe renamed .docx must be refused")


async def _upload(
    client: AsyncClient, h: dict[str, str], name: str, data: bytes, ctype: str
) -> dict:  # type: ignore[type-arg]
    r = await client.post(
        f"{API}/knowledge/documents", files={"file": (name, data, ctype)}, headers=h
    )
    assert r.status_code == 201, r.text
    doc = (await client.get(f"{API}/knowledge/documents/{r.json()['id']}", headers=h)).json()
    return dict(doc)


async def test_upload_search_and_cited_answer(client: AsyncClient, model: ScriptedProvider) -> None:
    h = await auth_headers(client)
    model.push("A runbook for incident response.")  # summary
    doc = await _upload(
        client,
        h,
        "runbook.docx",
        _docx(),
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    )
    assert doc["status"] == "ready" and doc["chunks"] >= 1
    assert doc["summary"] == "A runbook for incident response."
    model.push("Sheet with vulns.")
    sheet = await _upload(client, h, "vulns.xlsx", _xlsx(), "application/octet-stream")
    assert sheet["status"] == "ready" and sheet["preview"][0]["label"] == "Vulns"

    hits = (await client.get(f"{API}/knowledge/search?q=rotate keys breach", headers=h)).json()
    assert hits and hits[0]["title"] == "runbook"

    model.push("Rotate the API keys within 24 hours of a confirmed breach [1].")
    r = await client.post(
        f"{API}/knowledge/ask",
        json={"question": "When do we rotate keys after a breach?"},
        headers=h,
    )
    out = r.json()
    assert "[1]" in out["answer"] and out["citations"][0]["title"] == "runbook"
    prompt = model.requests[-1].messages[0]["content"]
    assert "<passages>" in prompt and "untrusted" in model.requests[-1].system[0]["text"]

    # the same file can't be added twice
    r = await client.post(
        f"{API}/knowledge/documents",
        files={"file": ("again.docx", _docx(), "application/octet-stream")},
        headers=h,
    )
    assert r.status_code == 400 and "already added" in r.json()["error"]["message"]

    assert (
        await client.delete(f"{API}/knowledge/documents/{doc['id']}", headers=h)
    ).status_code == 204
    r = await client.post(
        f"{API}/knowledge/ask", json={"question": "rotate keys breach?"}, headers=h
    )
    assert r.json()["citations"] == []


async def test_bad_files_and_images_without_vision(
    client: AsyncClient, model: ScriptedProvider
) -> None:
    h = await auth_headers(client)
    r = await client.post(
        f"{API}/knowledge/documents",
        files={"file": ("tool.exe", b"MZ\x90\x00binary", "application/octet-stream")},
        headers=h,
    )
    assert r.status_code == 400
    png = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64
    doc = await _upload(client, h, "whiteboard.png", png, "image/png")
    assert doc["status"] == "failed" and "vision model" in doc["error"]


async def test_assistant_can_search_documents(client: AsyncClient, model: ScriptedProvider) -> None:
    h = await auth_headers(client)
    model.push("Summary.")
    await _upload(
        client, h, "notes.txt", b"The VPN gateway is vpn.corp.example on port 443.", "text/plain"
    )
    cid = (await client.post(f"{API}/chat/conversations", headers=h)).json()["id"]
    model.push(
        [{"name": "kb_search", "input": {"query": "VPN gateway port"}}], "It's on port 443 (notes)."
    )
    r = await client.post(
        f"{API}/chat/conversations/{cid}/messages",
        json={"text": "what port is the vpn?"},
        headers=h,
    )
    assert '"tool.finished"' in r.text and "vpn.corp.example" in r.text
