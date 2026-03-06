from locust import HttpUser, between, task


class APIStressTest(HttpUser):
    """
    Simulates high traffic against the SkillSwarm/SocraticBridge backend
    to test the SlowAPI rate-limits and overall buffer stability.
    """

    # Wait between 1 and 2 seconds between tasks
    wait_time = between(1, 2)

    @task(3)
    def test_health_check(self):
        self.client.get("/health")

    @task(1)
    def test_blockchain_balance(self):
        # We assume user_id 1 exists for fetching balance
        with self.client.get(
            "/api/v1/blockchain/balance/1", catch_response=True
        ) as response:
            if response.status_code == 429:
                response.success()  # 429 is expected during stress due to SlowAPI
            elif response.status_code == 200:
                response.success()
            else:
                response.failure(f"Got unexpected status {response.status_code}")

    @task(1)
    def test_adapta_transform(self):
        payload = {"text": "This is a simple sentence."}
        with self.client.post(
            "/api/v1/adapta/transform", json=payload, catch_response=True
        ) as response:
            if response.status_code == 429:
                response.success()
            elif response.status_code == 200:
                response.success()
            else:
                response.failure(f"Got unexpected status {response.status_code}")
