"""Router de recomendaciones de docentes para cursos."""

import csv
import io
import logging
import re
import unicodedata
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from fpdf import FPDF
from sqlalchemy.orm import Session

from backend.api.deps import get_current_user, get_user_workspaces
from backend.database.db_session import get_db
from backend.database import crud
from backend.services.recommendation_engine import recommendation_engine

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/recommend", tags=["recommendations"])

# Helvetica (fuentes core de FPDF) solo soporta Latin-1. Las explicaciones usan
# "•" y a veces comillas tipográficas que rompen el export.
_PDF_CHAR_MAP = str.maketrans({
  "•": "-",
  "·": "-",
  "–": "-",
  "—": "-",
  "“": '"',
  "”": '"',
  "‘": "'",
  "’": "'",
  "…": "...",
  "\u00a0": " ",
  "\t": " ",
})


def _pdf_text(value) -> str:
  """Normaliza texto para fuentes core de FPDF (Helvetica / Latin-1)."""
  if value is None:
    return ""
  text = str(value).translate(_PDF_CHAR_MAP)
  text = unicodedata.normalize("NFC", text)
  # Cualquier otro Unicode no representable en Helvetica se sustituye
  return text.encode("latin-1", errors="replace").decode("latin-1")


@router.get("/docentes/{curso_id}")
async def recommend_docentes(
  curso_id: int,
  top_k: int = 100,
  user: dict = Depends(get_current_user),
  db: Session = Depends(get_db),
  workspaces: list = Depends(get_user_workspaces),
):
  try:
    curso = crud.get_curso_by_id(db, curso_id)
    if not curso:
      raise HTTPException(status_code=404, detail=f"Curso con ID {curso_id} no encontrado")

    logger.info(f"Generando recomendaciones de docentes para curso: {curso.nombre}")
    recommendations = recommendation_engine.recommend_docentes_for_curso(db=db, curso_id=curso_id, top_k=top_k, workspaces=workspaces)

    return {
      "success": True,
      "curso_id": curso_id,
      "curso_nombre": curso.nombre,
      "total_recommendations": len(recommendations),
      "recommendations": recommendations,
    }
  except Exception as e:
    logger.error(f" Error generando recomendaciones de docentes: {e}", exc_info=True)
    raise HTTPException(status_code=500, detail=f"Error generando recomendaciones: {str(e)}")


@router.get("/docentes/{curso_id}/export_pdf")
async def export_curso_recommendations_pdf(
  curso_id: int,
  user: dict = Depends(get_current_user),
  db: Session = Depends(get_db),
  workspaces: list = Depends(get_user_workspaces),
):
  try:
    curso = crud.get_curso_by_id(db, curso_id)
    if not curso:
      raise HTTPException(status_code=404, detail=f"Curso con ID {curso_id} no encontrado")

    recommendations = recommendation_engine.recommend_docentes_for_curso(db=db, curso_id=curso_id, top_k=20, workspaces=workspaces)

    pdf = FPDF()
    pdf.set_auto_page_break(auto=True, margin=20)
    pdf.add_page()

    pdf.set_fill_color(24, 24, 27)
    pdf.rect(0, 0, 210, 45, "F")
    pdf.set_text_color(255, 255, 255)
    pdf.set_font("Helvetica", "B", 20)
    pdf.set_y(10)
    pdf.cell(0, 10, _pdf_text("RANKING DE DOCENTES"), align="C", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 12)
    pdf.cell(0, 8, _pdf_text((curso.nombre or "").upper()), align="C", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 9)
    pdf.cell(
      0,
      6,
      _pdf_text(f'Ciclo {curso.ciclo or "N/A"} | Generado por Vektora'),
      align="C",
      new_x="LMARGIN",
      new_y="NEXT",
    )

    pdf.set_y(50)
    pdf.set_text_color(0, 0, 0)

    if not recommendations:
      pdf.set_font("Helvetica", "I", 12)
      pdf.cell(0, 10, _pdf_text("No hay recomendaciones disponibles para este curso."), align="C")
    else:
      for idx, rec in enumerate(recommendations):
        if pdf.get_y() > 230:
          pdf.add_page()
          pdf.set_y(15)

        y_start = pdf.get_y()
        card_x = 10
        card_w = 190

        pdf.set_font("Helvetica", "B", 24)
        pdf.set_text_color(180, 180, 180)
        pdf.set_xy(card_x + 2, y_start + 2)
        pdf.cell(15, 12, str(idx + 1), align="C")

        pdf.set_font("Helvetica", "B", 13)
        pdf.set_text_color(24, 24, 27)
        pdf.set_xy(card_x + 20, y_start + 2)
        nombre_display = rec.get("nombre", "").title() if rec.get("nombre") else "Sin nombre"
        pdf.cell(120, 7, _pdf_text(nombre_display), align="L")

        pdf.set_font("Helvetica", "", 8)
        pdf.set_text_color(120, 120, 120)
        pdf.set_xy(card_x + 20, y_start + 9)
        pdf.cell(120, 5, "", align="L")

        score = rec.get("score_combinado", 0)
        pdf.set_font("Helvetica", "B", 14)
        if idx == 0:
          pdf.set_fill_color(234, 239, 255)
          pdf.set_text_color(67, 56, 202)
        else:
          pdf.set_fill_color(243, 244, 246)
          pdf.set_text_color(24, 24, 27)
        pdf.set_xy(card_x + 155, y_start + 2)
        pdf.cell(30, 10, f"{score:.0f}%", align="C", fill=True)

        conf = rec.get("confianza_etiqueta", "") or ""
        pdf.set_font("Helvetica", "", 8)
        if "Muy Alta" in conf:
          pdf.set_text_color(21, 128, 61)
        elif "Alta" in conf:
          pdf.set_text_color(29, 78, 216)
        elif "Media" in conf:
          pdf.set_text_color(161, 98, 7)
        else:
          pdf.set_text_color(220, 38, 38)
        pdf.set_xy(card_x + 20, y_start + 16)
        pdf.cell(60, 5, _pdf_text(conf), align="L")

        pdf.set_text_color(100, 100, 100)
        pdf.set_font("Helvetica", "", 7)
        pdf.set_xy(card_x + 80, y_start + 16)
        sem = rec.get("score_semantico", rec.get("score_est", 0)) or 0
        tac = rec.get("score_historico", rec.get("score_tac", 0)) or 0
        rel = rec.get("score_relativo", 0) or 0
        pdf.cell(80, 5, _pdf_text(f"Sem: {sem:.0f}% | Tac: {tac:.0f}% | Rel: {rel:.0f}%"), align="L")

        xai = rec.get("xai_explanations", "") or ""
        if xai:
          pdf.set_font("Helvetica", "", 8)
          pdf.set_text_color(55, 65, 81)
          pdf.set_xy(card_x + 20, y_start + 23)
          pdf.multi_cell(165, 4, _pdf_text(xai), align="L")

        current_y = pdf.get_y() + 3
        pdf.set_draw_color(229, 231, 235)
        pdf.line(card_x + 5, current_y, card_x + card_w - 5, current_y)
        pdf.set_y(current_y + 5)

    pdf_bytes = pdf.output()
    output_buffer = io.BytesIO(pdf_bytes)
    output_buffer.seek(0)

    safe_name = re.sub(r"[^\w\-]+", "_", (curso.nombre or "curso"), flags=re.UNICODE)[:30]
    filename = f"ranking_{safe_name}.pdf"
    return StreamingResponse(
      output_buffer,
      media_type="application/pdf",
      headers={"Content-Disposition": f"attachment; filename={filename}"},
    )
  except HTTPException:
    raise
  except Exception as e:
    logger.error(f"Error exportando PDF: {e}", exc_info=True)
    raise HTTPException(status_code=500, detail=f"Error exportando PDF: {str(e)}")


@router.get("/admin/export_recommendations")
async def export_all_recommendations(
  user: dict = Depends(get_current_user),
  db: Session = Depends(get_db),
  workspaces: list = Depends(get_user_workspaces),
):
  try:
    logger.info("Iniciando exportacion masiva de recomendaciones...")
    cursos = crud.get_all_cursos(db, skip=0, limit=1000, workspaces=workspaces)
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
      "Curso ID", "Curso Nombre", "Ciclo", "Docente ID", "Docente Nombre",
      "Grado", "Score Combinado (%)", "Score Semantico (%)",
      "Score Tactico (%)", "Score Relativo (%)", "Confianza", "Explicacion IA",
    ])

    for curso in cursos:
      logger.info(f" Generando/obteniendo recomendaciones para curso: {curso.nombre}")
      recommendations = recommendation_engine.recommend_docentes_for_curso(db=db, curso_id=curso.id, top_k=20, workspaces=workspaces)

      if not recommendations:
        writer.writerow([curso.id, curso.nombre, curso.ciclo or "N/A", "N/A", "Sin docentes recomendados", "", "0", "0", "0", "0", "", ""])
        continue

      for rec in recommendations:
        writer.writerow([
          curso.id,
          curso.nombre,
          curso.ciclo or "N/A",
          rec.get("docente_id", ""),
          rec.get("nombre", ""),
          rec.get("grado", ""),
          rec.get("score_combinado", 0),
          rec.get("score_semantico", 0),
          rec.get("score_historico", 0),
          rec.get("score_relativo", 0),
          rec.get("confianza_etiqueta", ""),
          rec.get("xai_explanations", "").replace("\n", " "),
        ])

    output.seek(0)
    logger.info(" Exportación completa, enviando CSV.")
    return StreamingResponse(
      iter([output.getvalue()]),
      media_type="text/csv",
      headers={"Content-Disposition": "attachment; filename=recomendaciones_completas.csv"},
    )
  except Exception as e:
    logger.error(f" Error exportando recomendaciones: {e}", exc_info=True)
    raise HTTPException(status_code=500, detail=f"Error exportando: {str(e)}")
