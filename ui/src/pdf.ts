import html2canvas from "html2canvas-pro";
import { jsPDF } from "jspdf";

// A4 portrait in mm, and the CSS width the report is laid out at for the PDF (independent of the window).
const PAGE_W = 210;
const PAGE_H = 297;
const MARGIN = 12;
const FOOTER = 8;
const SHEET_PX = 820;
const SCALE = 2;

// Elements a page may start at, so page breaks fall between cards, rows and list items, not through them.
const BREAKABLE = ":scope > *, section, .condition, .metric, tr, li, h2, h3, p, .profile, .outcome, .banner";

/**
 * Saves what the report shows as a PDF. The view is cloned off-screen at a fixed width, rendered
 * once, and cut into A4 pages at element boundaries; a header (title, child, date) is added on top
 * and page numbers at the bottom.
 */
export async function downloadReportPdf(
  source: HTMLElement,
  { filename, title, lines }: { filename: string; title: string; lines: string[] },
): Promise<void> {
  const sheet = document.createElement("div");
  sheet.className = "pdf-sheet";
  sheet.style.width = `${SHEET_PX}px`;
  const header = document.createElement("header");
  header.className = "pdf-header";
  header.innerHTML = `<div class="pdf-brand">Omli · Developmental screening</div><h1></h1><div class="pdf-meta"></div>`;
  header.querySelector("h1")!.textContent = title;
  header.querySelector(".pdf-meta")!.textContent = lines.join("  ·  ");
  sheet.append(header, ...Array.from(source.cloneNode(true).childNodes));
  document.body.append(sheet);

  try {
    await document.fonts.ready;
    const top = sheet.getBoundingClientRect().top;
    // Never start a page right after a heading, so a heading stays with what it introduces.
    const breaks = Array.from(sheet.querySelectorAll<HTMLElement>(BREAKABLE))
      .filter((el) => !/^H[1-3]$/.test(el.previousElementSibling?.tagName ?? ""))
      .map((el) => Math.round(el.getBoundingClientRect().top - top))
      .filter((y) => y > 0);
    const total = sheet.scrollHeight;
    const canvas = await html2canvas(sheet, { scale: SCALE, backgroundColor: "#ffffff", useCORS: true, logging: false });

    const contentW = PAGE_W - 2 * MARGIN;
    const contentH = PAGE_H - 2 * MARGIN - FOOTER;
    const pagePx = Math.floor((contentH / contentW) * SHEET_PX);
    const cuts = [...new Set(breaks)].sort((a, b) => a - b);

    const slices: [number, number][] = [];
    for (let start = 0; start < total - 4; ) {
      const limit = start + pagePx;
      if (limit >= total) {
        slices.push([start, total]);
        break;
      }
      // Latest element start that still fits; cut mid-element only if nothing fits in the top third.
      const fit = cuts.filter((y) => y > start + pagePx / 3 && y <= limit).pop();
      const end = fit ?? limit;
      slices.push([start, end]);
      start = end;
    }

    const pdf = new jsPDF({ unit: "mm", format: "a4", compress: true });
    const piece = document.createElement("canvas");
    piece.width = canvas.width;
    slices.forEach(([a, b], i) => {
      if (i > 0) pdf.addPage();
      piece.height = Math.ceil((b - a) * SCALE);
      const ctx = piece.getContext("2d")!;
      ctx.fillStyle = "#ffffff";
      ctx.fillRect(0, 0, piece.width, piece.height);
      ctx.drawImage(canvas, 0, a * SCALE, canvas.width, piece.height, 0, 0, piece.width, piece.height);
      pdf.addImage(piece.toDataURL("image/jpeg", 0.92), "JPEG", MARGIN, MARGIN, contentW, ((b - a) / SHEET_PX) * contentW);
      pdf.setFontSize(8);
      pdf.setTextColor(120);
      pdf.text(`${title} · page ${i + 1} of ${slices.length}`, MARGIN, PAGE_H - MARGIN + 2);
      pdf.text("Screening result, not a diagnosis", PAGE_W - MARGIN, PAGE_H - MARGIN + 2, { align: "right" });
    });
    pdf.save(filename);
  } finally {
    sheet.remove();
  }
}
