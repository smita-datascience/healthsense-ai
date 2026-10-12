"""WhatsApp Cloud API channel for HealthSense AI (v2).

A thin delivery layer: it receives WhatsApp messages, hands the text to the
existing crew (`app.agents.crew.answer`) unchanged, and sends the reply back.
All safety guarantees stay in the crew; this package adds none and removes none.
"""
