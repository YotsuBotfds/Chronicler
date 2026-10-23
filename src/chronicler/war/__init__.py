"""M60 production campaigns: armies, logistics, battles, occupation and peace.

Default-off behind ``WorldState.campaigns_enabled`` (CLI ``--campaigns``).
The per-turn entry point is :func:`chronicler.war.runtime.tick_campaigns`;
the WAR action hook is :func:`chronicler.war.runtime.declare_or_press_war`.
Design notes live in ``docs/war/campaigns-battles-occupation.md``.

This package ``__init__`` deliberately imports nothing so that
``chronicler.models`` can be imported without the campaign layer.
"""
