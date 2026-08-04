"""Agendador diário do DevRecap.

Dispara o `callback` (geração do resumo do dia) num horário fixo, em dias úteis
por padrão. Usa o `BackgroundScheduler` do APScheduler, que roda numa thread
separada e não bloqueia o app de bandeja.

O `callback` é chamado sem argumentos. Nenhuma exceção dele derruba o scheduler:
o `_wrap` captura e loga tudo.
"""
from __future__ import annotations

from typing import Callable, Optional

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

from devrecap.core.logging_setup import get_logger

log = get_logger(__name__)

JOB_ID = "daily_recap"
DEFAULT_TIME = "18:00"


def _parse_time(time_str: str) -> tuple[int, int]:
    """Parseia "HH:MM" -> (hour, minute). Cai em 18:00 se inválido."""
    try:
        parts = (time_str or "").strip().split(":")
        if len(parts) != 2:
            raise ValueError(f"formato esperado HH:MM, recebido: {time_str!r}")
        hour = int(parts[0])
        minute = int(parts[1])
        if not (0 <= hour <= 23 and 0 <= minute <= 59):
            raise ValueError(f"hora/minuto fora do intervalo: {hour}:{minute}")
        return hour, minute
    except (ValueError, AttributeError, TypeError) as exc:
        log.warning("time_str inválido (%r): %s. Usando %s.", time_str, exc, DEFAULT_TIME)
        h, m = DEFAULT_TIME.split(":")
        return int(h), int(m)


class DailyScheduler:
    """Agenda a geração diária do resumo num horário fixo."""

    def __init__(
        self,
        callback: Callable[[], None],
        *,
        time_str: str = "18:00",
        run_on_weekends: bool = False,
    ) -> None:
        """Guarda o callback e prepara o BackgroundScheduler (timezone local)."""
        self._callback = callback
        self._time_str = time_str
        self._run_on_weekends = run_on_weekends
        self._hour, self._minute = _parse_time(time_str)
        self._scheduler = BackgroundScheduler()

    # ------------------------------------------------------------------ #
    def _day_of_week(self) -> str:
        """Expressão de dias da semana conforme run_on_weekends."""
        return "*" if self._run_on_weekends else "mon-fri"

    def _wrap(self) -> None:
        """Executa o callback protegido — nunca derruba o scheduler."""
        try:
            self._callback()
        except Exception as exc:  # noqa: BLE001 — agendador não pode cair
            log.exception("Erro no callback do agendamento diário: %s", exc)

    # ------------------------------------------------------------------ #
    def start(self) -> None:
        """Inicia o scheduler e registra o job diário."""
        try:
            if not self._scheduler.running:
                self._scheduler.start()
            self._scheduler.add_job(
                self._wrap,
                CronTrigger(
                    hour=self._hour,
                    minute=self._minute,
                    day_of_week=self._day_of_week(),
                ),
                id=JOB_ID,
                replace_existing=True,
            )
            log.info(
                "Agendamento diário ativo: %02d:%02d (%s).",
                self._hour,
                self._minute,
                self._day_of_week(),
            )
        except Exception as exc:  # noqa: BLE001
            log.exception("Falha ao iniciar o agendamento diário: %s", exc)

    def reschedule(self, time_str: str, run_on_weekends: bool) -> None:
        """Re-parseia o horário e re-registra o job com o novo gatilho."""
        try:
            self._time_str = time_str
            self._run_on_weekends = run_on_weekends
            self._hour, self._minute = _parse_time(time_str)
            if not self._scheduler.running:
                self._scheduler.start()
            self._scheduler.add_job(
                self._wrap,
                CronTrigger(
                    hour=self._hour,
                    minute=self._minute,
                    day_of_week=self._day_of_week(),
                ),
                id=JOB_ID,
                replace_existing=True,
            )
            log.info(
                "Agendamento diário reagendado: %02d:%02d (%s).",
                self._hour,
                self._minute,
                self._day_of_week(),
            )
        except Exception as exc:  # noqa: BLE001
            log.exception("Falha ao reagendar o agendamento diário: %s", exc)

    def next_run_time(self):
        """Próxima execução do job (datetime) ou None se não houver."""
        try:
            job = self._scheduler.get_job(JOB_ID)
            return job.next_run_time if job is not None else None
        except Exception as exc:  # noqa: BLE001
            log.exception("Falha ao obter próxima execução: %s", exc)
            return None

    def shutdown(self) -> None:
        """Encerra o scheduler sem esperar jobs em andamento."""
        try:
            if self._scheduler.running:
                self._scheduler.shutdown(wait=False)
                log.info("Agendamento diário encerrado.")
        except Exception as exc:  # noqa: BLE001
            log.exception("Falha ao encerrar o agendamento diário: %s", exc)
