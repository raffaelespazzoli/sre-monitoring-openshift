from locust import HttpLocust, TaskSet, task


class MyTaskSet(TaskSet):

    def on_start(self):
        """ on_start is called when a Locust start before any task is scheduled """
        self.client.verify = False
        self.login()

    @task(1)
    def refresh100(self):
        for x in range(1, 100):
            self.client.get("/productpage")

    def login(self):
        self.client.get("/productpage")
        self.client.post("/login", {"username": "hello", "password": "ciao"})


class MyLocust(HttpLocust):
    task_set = MyTaskSet
    min_wait = 500
    max_wait = 1500
