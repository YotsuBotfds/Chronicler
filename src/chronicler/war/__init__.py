"""M60 production campaigns: armies, logistics, battles, occupation and peace.

New CLI, batch and live worlds enable campaigns by default; ``--no-campaigns``
opts out. ``WorldState.campaigns_enabled`` itself defaults off so legacy and
directly constructed worlds retain instant war resolution.
The per-turn entry point is :func:`chronicler.war.runtime.tick_campaigns`;
the WAR action hook is :func:`chronicler.war.runtime.declare_or_press_war`.
Design notes live in ``docs/war/campaigns-battles-occupation.md``.

This package ``__init__`` deliberately imports nothing so that
``chronicler.models`` can be imported without the campaign layer.
"""
