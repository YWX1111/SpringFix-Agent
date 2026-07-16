CREATE TABLE IF NOT EXISTS orders (
    id BIGINT PRIMARY KEY,
    customer VARCHAR(255),
    amount DECIMAL(19, 2)
);
