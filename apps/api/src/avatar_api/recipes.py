"""Registro da receita congelada do worker como a receita vigente da API.

Receita gravada nunca muda (recipe_frozen_per_job): trocar modelo, voz ou parâmetro
cria uma receita com outro nome.
"""

from typing import Any

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from avatar_api.models import RenderRecipe


class RecipeLoadError(Exception):
    """Receita recusada, com mensagem em português pronta para o operador."""


def _max_script_chars(spec: dict[str, Any]) -> int:
    limits = spec.get("limits")
    value = limits.get("max_script_chars") if isinstance(limits, dict) else None
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise RecipeLoadError("A receita precisa de limits.max_script_chars inteiro positivo.")
    return value


def _validated(spec: Any) -> tuple[str, int]:
    if not isinstance(spec, dict):
        raise RecipeLoadError("A receita precisa ser um objeto JSON.")
    if spec.get("status") != "frozen":
        raise RecipeLoadError("Só receita congelada (status frozen) pode ser carregada.")
    name = spec.get("name")
    if not isinstance(name, str) or not name.strip():
        raise RecipeLoadError("A receita precisa de um name não vazio.")
    return name, _max_script_chars(spec)


def load_frozen_recipe(session: Session, spec: Any) -> RenderRecipe:
    """Grava a receita congelada e a torna a única vigente, numa transação só."""
    name, max_script_chars = _validated(spec)
    recipe = session.scalar(select(RenderRecipe).where(RenderRecipe.name == name))
    if recipe is not None and recipe.spec != spec:
        raise RecipeLoadError(
            f"Já existe a receita {name} com conteúdo diferente; receita gravada nunca muda."
        )
    # A vigente anterior sai antes de a nova entrar, por causa do índice único parcial.
    session.execute(
        update(RenderRecipe)
        .where(RenderRecipe.is_current, RenderRecipe.name != name)
        .values(is_current=False)
    )
    if recipe is None:
        recipe = RenderRecipe(name=name, max_script_chars=max_script_chars, spec=spec)
        session.add(recipe)
    recipe.is_current = True
    try:
        session.commit()
    except IntegrityError as exc:
        session.rollback()
        raise RecipeLoadError(
            f"A receita {name} foi alterada por outra carga; tente de novo."
        ) from exc
    return recipe
