import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from avatar_api.config import Settings
from avatar_api.devseed import DevCatalog
from avatar_api.models import RenderRecipe
from avatar_api.recipes import RecipeLoadError, load_frozen_recipe

AVATAR_API = Path(sys.executable).parent / "avatar-api"
RECIPE_V1 = Path(__file__).resolve().parents[4] / "docs" / "models" / "RECIPE-v1.json"


def frozen_recipe(name: str = "RECIPE-v1", max_script_chars: int = 480) -> dict[str, Any]:
    """RECIPE-v1.json em memória com status frozen; o arquivo não é alterado."""
    spec = json.loads(RECIPE_V1.read_text())
    spec.update(name=name, status="frozen")
    spec["limits"]["max_script_chars"] = max_script_chars
    return spec


def rows(session: Session) -> list[tuple]:
    session.expire_all()
    recipes = session.scalars(select(RenderRecipe).order_by(RenderRecipe.name))
    return [(r.id, r.name, r.max_script_chars, r.spec, r.is_current) for r in recipes]


def current_names(session: Session) -> list[str]:
    return [name for _, name, _, _, is_current in rows(session) if is_current]


def run_recipes_load(database_url: str, stdin: str) -> subprocess.CompletedProcess:
    env = {**os.environ, "DATABASE_URL": database_url}
    return subprocess.run(
        [str(AVATAR_API), "recipes", "load"],
        input=stdin,
        capture_output=True,
        text=True,
        env=env,
        timeout=60,
    )


def test_receita_congelada_vira_a_unica_vigente(session: Session, seeded_catalog: DevCatalog):
    assert current_names(session) == ["dev-seed"]

    recipe = load_frozen_recipe(session, frozen_recipe())

    assert current_names(session) == ["RECIPE-v1"]
    stored = session.get(RenderRecipe, recipe.id)
    assert stored.max_script_chars == 480
    assert stored.spec == frozen_recipe()


def test_recarga_identica_reafirma_a_vigencia(session: Session):
    first = load_frozen_recipe(session, frozen_recipe())
    load_frozen_recipe(session, frozen_recipe("RECIPE-v2"))
    assert current_names(session) == ["RECIPE-v2"]

    again = load_frozen_recipe(session, frozen_recipe())

    assert again.id == first.id
    assert current_names(session) == ["RECIPE-v1"]
    assert len(rows(session)) == 2


def test_mesmo_nome_com_spec_diferente_recusado_sem_mudar_linhas(session: Session):
    load_frozen_recipe(session, frozen_recipe())
    load_frozen_recipe(session, frozen_recipe("RECIPE-v2"))
    before = rows(session)

    with pytest.raises(RecipeLoadError, match="nunca muda"):
        load_frozen_recipe(session, frozen_recipe(max_script_chars=900))

    assert rows(session) == before


@pytest.mark.parametrize(
    ("change", "message"),
    [
        (lambda s: s.update(status="draft"), "status frozen"),
        (lambda s: s.pop("status"), "status frozen"),
        (lambda s: s.update(name=""), "name não vazio"),
        (lambda s: s.update(name="   "), "name não vazio"),
        (lambda s: s.pop("name"), "name não vazio"),
        (lambda s: s["limits"].update(max_script_chars=0), "inteiro positivo"),
        (lambda s: s["limits"].update(max_script_chars="600"), "inteiro positivo"),
        (lambda s: s["limits"].update(max_script_chars=True), "inteiro positivo"),
        (lambda s: s["limits"].pop("max_script_chars"), "inteiro positivo"),
        (lambda s: s.pop("limits"), "inteiro positivo"),
    ],
)
def test_receita_invalida_recusada_sem_mudar_linhas(
    session: Session, seeded_catalog: DevCatalog, change, message: str
):
    spec = frozen_recipe()
    change(spec)
    before = rows(session)

    with pytest.raises(RecipeLoadError, match=message):
        load_frozen_recipe(session, spec)

    assert rows(session) == before


def test_cli_grava_a_receita_e_imprime_id_e_nome(session: Session, settings: Settings):
    result = run_recipes_load(settings.database_url, json.dumps(frozen_recipe()))

    assert result.returncode == 0, result.stderr
    recipe_id, name = result.stdout.split()
    assert name == "RECIPE-v1"
    assert [(str(r[0]), r[1], r[2], r[4]) for r in rows(session)] == [
        (recipe_id, "RECIPE-v1", 480, True)
    ]

    again = run_recipes_load(settings.database_url, json.dumps(frozen_recipe()))

    assert again.returncode == 0, again.stderr
    assert again.stdout == result.stdout


def test_cli_recusa_rascunho(session: Session, settings: Settings, seeded_catalog: DevCatalog):
    before = rows(session)

    result = run_recipes_load(settings.database_url, RECIPE_V1.read_text())

    assert result.returncode == 1
    assert "status frozen" in result.stderr
    assert result.stdout == ""
    assert rows(session) == before


def test_cli_recusa_spec_divergente_com_mesmo_nome(session: Session, settings: Settings):
    assert run_recipes_load(settings.database_url, json.dumps(frozen_recipe())).returncode == 0
    before = rows(session)

    result = run_recipes_load(
        settings.database_url, json.dumps(frozen_recipe(max_script_chars=900))
    )

    assert result.returncode == 1
    assert "nunca muda" in result.stderr
    assert result.stdout == ""
    assert rows(session) == before


def test_cli_recusa_json_invalido(session: Session, settings: Settings):
    result = run_recipes_load(settings.database_url, "{não é json")

    assert result.returncode == 1
    assert "JSON válido" in result.stderr
    assert rows(session) == []
