"""Invariantes deterministas del agregador de Kilómetro Cero.

Los valores esperados provienen de source/simulation.py y de su fixture
synthetic data/scenarios.json: no se añaden umbrales externos.
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[1]
RUTA_SIMULACION = RAIZ / "source" / "simulation.py"


def _cargar_simulacion():
    especificacion = importlib.util.spec_from_file_location("kilometro_simulation", RUTA_SIMULACION)
    modulo = importlib.util.module_from_spec(especificacion)
    especificacion.loader.exec_module(modulo)
    return modulo


simulacion = _cargar_simulacion()
simulate = simulacion.simulate
DATA = simulacion.DATA
CORREDORES = {fila["id"]: fila for fila in DATA["corridors"]}
INCIDENTES = {fila["id"]: fila for fila in DATA["incidents"]}


def test_fixture_base_es_coherente():
    total_envios = sum(fila["shipments"] for fila in DATA["corridors"])
    assert total_envios == 642
    assert len(DATA["corridors"]) == 12
    for fila in DATA["corridors"]:
        assert fila["on_time"] + fila["delayed"] + fila["at_risk"] == fila["shipments"]


def test_misma_entrada_mismo_resultado():
    for incidente in INCIDENTES:
        for filtro in ("all", "on_time", "delayed", "at_risk"):
            primero = simulate(incidente, filtro)
            segundo = simulate(incidente, filtro)
            assert primero == segundo
            assert primero["corridors"] == segundo["corridors"]


def test_totales_conservan_los_envios_del_fixture():
    base = simulate("none")
    assert base["totals"] == {
        "shipments": 642,
        "on_time": 551,
        "delayed": 68,
        "at_risk": 23,
        "corridors": 12,
    }
    for incidente in INCIDENTES:
        resultado = simulate(incidente)
        assert resultado["totals"]["shipments"] == 642
        for fila in resultado["corridors"]:
            assert fila["on_time"] + fila["delayed"] + fila["at_risk"] == fila["shipments"]


def test_closure_mueve_envios_de_a_tiempo_a_demora():
    base = {fila["id"]: fila for fila in simulate("none")["corridors"]}
    resultado = simulate("closure")
    afectados = set(INCIDENTES["closure"]["affected_corridors"])
    assert afectados <= set(CORREDORES)
    for fila in resultado["corridors"]:
        referencia = base[fila["id"]]
        if fila["id"] in afectados:
            desplazados = min(
                max(3, round(referencia["shipments"] * 0.10)), referencia["on_time"]
            )
            assert fila["on_time"] == referencia["on_time"] - desplazados
            assert fila["delayed"] == referencia["delayed"] + desplazados
            assert fila["at_risk"] == referencia["at_risk"]
        else:
            assert (fila["on_time"], fila["delayed"], fila["at_risk"]) == (
                referencia["on_time"],
                referencia["delayed"],
                referencia["at_risk"],
            )
    assert resultado["totals"]["on_time"] <= simulate("none")["totals"]["on_time"]
    assert resultado["totals"]["delayed"] >= simulate("none")["totals"]["delayed"]
    assert resultado["totals"]["at_risk"] == simulate("none")["totals"]["at_risk"]


def test_storm_aumenta_el_riesgo_sin_cambiar_los_totales():
    base = {fila["id"]: fila for fila in simulate("none")["corridors"]}
    resultado = simulate("storm")
    afectados = set(INCIDENTES["storm"]["affected_corridors"])
    assert afectados <= set(CORREDORES)
    for fila in resultado["corridors"]:
        referencia = base[fila["id"]]
        if fila["id"] in afectados:
            desplazados = min(
                max(3, round(referencia["shipments"] * 0.08)), referencia["on_time"]
            )
            demora = referencia["delayed"] + desplazados
            riesgo = min(demora, max(1, round(referencia["shipments"] * 0.025)))
            assert fila["on_time"] == referencia["on_time"] - desplazados
            assert fila["delayed"] == demora - riesgo
            assert fila["at_risk"] == referencia["at_risk"] + riesgo
        else:
            assert (fila["on_time"], fila["delayed"], fila["at_risk"]) == (
                referencia["on_time"],
                referencia["delayed"],
                referencia["at_risk"],
            )
    assert resultado["totals"]["at_risk"] >= simulate("none")["totals"]["at_risk"]
    assert resultado["totals"]["shipments"] == 642


def test_filtros_solo_muestran_el_estado_elegido():
    for filtro in ("on_time", "delayed", "at_risk"):
        resultado = simulate("none", filtro)
        assert resultado["filter"] == filtro
        assert resultado["corridors"]
        for fila in resultado["corridors"]:
            assert fila["visible_shipments"] == fila[filtro]
            assert fila["visible_shipments"] > 0
        assert resultado["totals"]["shipments"] == sum(
            fila["visible_shipments"] for fila in resultado["corridors"]
        )
        assert resultado["totals"]["corridors"] == len(resultado["corridors"])


def test_seleccion_de_corredor():
    assert simulate("none")["selected_corridor"] is None
    seleccionado = simulate("none", "all", "tij-mty")["selected_corridor"]
    assert seleccionado is not None
    assert seleccionado["id"] == "tij-mty"
    assert seleccionado["visible_shipments"] == seleccionado["shipments"]


def test_entradas_invalidas_fallan():
    with pytest.raises(ValueError):
        simulate("incidente-inexistente")
    with pytest.raises(ValueError):
        simulate("none", "estado-inexistente")


def test_simular_no_muta_el_fixture():
    import copy

    copia = copy.deepcopy(DATA)
    simulate("closure")
    simulate("storm", "at_risk")
    assert DATA == copia
