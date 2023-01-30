db.createUser(
        {
            user: "admin",
            pwd: "pass1234",
            roles: [
                {
                    role: "readWrite",
                    db: "service_broker"
                }
            ]
        }
);
