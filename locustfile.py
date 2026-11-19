"""Locust stress test for HealthSense AI.

Hits the local FastAPI /ask endpoint directly (not via WhatsApp/ngrok).
Every request calls Claude for real, so start small (5 users).
"""
import random

from locust import HttpUser, between, task

SAFE_QUESTIONS = [
    "What helps with a mild headache?",
    "How much water should an adult drink in a day?",
    "What is a normal resting heart rate?",
    "What are common causes of a dry cough?",
    "Bukhar mein kya khana chahiye?",
]

EMERGENCY_QUESTIONS = [
    "I have crushing chest pain spreading to my left arm",
]


class HealthSenseUser(HttpUser):
    # Each simulated user waits 5-10 seconds between questions,
    # like a real person reading the answer.
    wait_time = between(5, 10)

    @task(5)
    def ask_safe_question(self):
        self._ask(random.choice(SAFE_QUESTIONS), name="/ask [safe]")

    @task(1)
    def ask_emergency_question(self):
        self._ask(random.choice(EMERGENCY_QUESTIONS), name="/ask [emergency]")

    def _ask(self, question, name):
        with self.client.post(
            "/ask",
            json={"question": question},
            name=name,
            timeout=120,  # Claude calls are slow; don't give up too early
            catch_response=True,
        ) as resp:
            if resp.status_code != 200:
                resp.failure(f"HTTP {resp.status_code}: {resp.text[:200]}")
            else:
                resp.success()