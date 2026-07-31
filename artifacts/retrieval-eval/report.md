# M3 Retrieval Evaluation Report

- Cases: 13
- Top-K: 5
- RRF k: 10
- Symbol weight: 1.0
- Generated: 2026-07-31 14:13:18

## Development Metrics

| Channel | Recall@1 | Recall@3 | Recall@5 | MRR@10 | Mean Query (ms) | P95 Query (ms) |
|---------|----------|----------|----------|--------|-----------------|----------------|
| baseline * | 0.6429 | 0.9286 | 0.9286 | 0.8571 | 2.857 | 6.000 |
| bm25 * | 0.6429 | 0.7143 | 0.7143 | 0.7143 | 0.200 | 0.499 |
| hybrid * | 0.6429 | 1.0000 | 1.0000 | 0.8571 | 10.520 | 17.533 |

## Holdout Metrics

| Channel | Recall@1 | Recall@3 | Recall@5 | MRR@10 | Mean Query (ms) | P95 Query (ms) |
|---------|----------|----------|----------|--------|-----------------|----------------|
| baseline * | 0.8333 | 1.0000 | 1.0000 | 0.9167 | 3.667 | 4.000 |
| bm25 * | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 0.149 | 0.219 |
| hybrid * | 0.8333 | 1.0000 | 1.0000 | 0.9167 | 14.598 | 20.148 |

## Per-Case Details

### retrieval-transaction-self-invocation (development)

- query_terms: ['transactional', 'self', 'invocation', 'bypass', 'create', 'order']
- exact_symbols: []

- **baseline**: R@1=1.00 R@3=1.00 R@5=1.00 MRR=1.00 (6.000ms, 4 hits)
  - first_relevant_rank: 0
  - [0] src/main/java/com/springfix/sample/transaction/service/OrderService.java L6-37 (file_window, score=29.0000, sources=['baseline'])
  - [1] src/test/java/com/springfix/sample/transaction/TransactionSelfInvocationTest.java L13-46 (file_window, score=21.0000, sources=['baseline'])
  - [2] pom.xml L15-18 (file_window, score=5.5000, sources=['baseline'])
  - [3] src/main/java/com/springfix/sample/transaction/Application.java L7-7 (file_window, score=1.0000, sources=['baseline'])
- **bm25**: R@1=0.00 R@3=0.00 R@5=0.00 MRR=0.00 (0.499ms, 0 hits)
  - first_relevant_rank: -1
- **symbol**: activated=False, hits=0, input=[]
  - first_relevant_rank: -1
- **hybrid**: R@1=0.00 R@3=1.00 R@5=1.00 MRR=0.50 (12.428ms, 4 hits)
  - symbol_activated=False, symbol_hits=0
  - first_relevant_rank: 1
  - [0] src/test/java/com/springfix/sample/transaction/TransactionSelfInvocationTest.java L14-46 (file_window, score=0.0164, sources=['baseline'])
  - [1] src/main/java/com/springfix/sample/transaction/service/OrderService.java L9-39 (file_window, score=0.0161, sources=['baseline'])
  - [2] pom.xml L15-18 (file_window, score=0.0159, sources=['baseline'])
  - [3] src/main/java/com/springfix/sample/transaction/Application.java L7-9 (file_window, score=0.0156, sources=['baseline'])

### retrieval-dependency-injection (development)

- query_terms: ['autowired', 'constructor', 'injection', 'jdbc', 'template', 'dependency', 'order', 'service']
- exact_symbols: ['OrderService', 'JdbcTemplate']

- **baseline**: R@1=0.00 R@3=1.00 R@5=1.00 MRR=0.50 (4.000ms, 2 hits)
  - first_relevant_rank: 1
  - [0] src/test/java/com/springfix/sample/transaction/TransactionSelfInvocationTest.java L5-28 (file_window, score=11.5000, sources=['baseline'])
  - [1] src/main/java/com/springfix/sample/transaction/service/OrderService.java L3-23 (file_window, score=11.0000, sources=['baseline'])
- **bm25**: R@1=1.00 R@3=1.00 R@5=1.00 MRR=1.00 (0.316ms, 5 hits)
  - first_relevant_rank: 0
  - [0] src/main/java/com/springfix/sample/transaction/service/OrderService.java L21-25 (constructor, score=3.5415, sources=['bm25'])
  - [1] pom.xml L36-49 (config_block, score=1.7906, sources=['bm25'])
  - [2] src/main/java/com/springfix/sample/transaction/service/OrderService.java L9-44 (class, score=1.5455, sources=['bm25'])
  - [3] src/test/java/com/springfix/sample/transaction/TransactionSelfInvocationTest.java L13-49 (class, score=1.4803, sources=['bm25'])
  - [4] pom.xml L1-40 (config_block, score=1.4043, sources=['bm25'])
- **symbol**: activated=True, hits=1, input=['OrderService', 'JdbcTemplate']
  - first_relevant_rank: 0
  - [0] src/main/java/com/springfix/sample/transaction/service/OrderService.java L18-44 (class, score=0.0000, sources=['symbol'])
- **hybrid**: R@1=1.00 R@3=1.00 R@5=1.00 MRR=1.00 (16.852ms, 5 hits)
  - symbol_activated=True, symbol_hits=1
  - first_relevant_rank: 0
  - [0] src/main/java/com/springfix/sample/transaction/service/OrderService.java L1-39 (file_window, score=0.0246, sources=['symbol', 'bm25', 'baseline'])
  - [1] src/test/java/com/springfix/sample/transaction/TransactionSelfInvocationTest.java L13-49 (class, score=0.0164, sources=['baseline', 'bm25'])
  - [2] pom.xml L1-40 (config_block, score=0.0161, sources=['baseline', 'bm25'])
  - [3] pom.xml L36-49 (config_block, score=0.0161, sources=['bm25'])
  - [4] src/main/resources/application.properties L1-1 (file_window, score=0.0156, sources=['baseline'])

### retrieval-config-binding (development)

- query_terms: ['spring', 'datasource', 'configuration', 'properties']
- exact_symbols: []

- **baseline**: R@1=0.00 R@3=1.00 R@5=1.00 MRR=0.50 (4.000ms, 5 hits)
  - first_relevant_rank: 1
  - [0] pom.xml L8-45 (file_window, score=11.0000, sources=['baseline'])
  - [1] src/main/resources/application.properties L1-6 (file_window, score=10.0000, sources=['baseline'])
  - [2] src/main/java/com/springfix/sample/transaction/service/OrderService.java L1-6 (file_window, score=5.0000, sources=['baseline'])
  - [3] src/test/java/com/springfix/sample/transaction/TransactionSelfInvocationTest.java L1-7 (file_window, score=5.0000, sources=['baseline'])
  - [4] src/main/java/com/springfix/sample/transaction/Application.java L1-4 (file_window, score=3.0000, sources=['baseline'])
- **bm25**: R@1=1.00 R@3=1.00 R@5=1.00 MRR=1.00 (0.103ms, 5 hits)
  - first_relevant_rank: 0
  - [0] src/main/resources/application.properties L1-6 (config_block, score=2.7834, sources=['bm25'])
  - [1] pom.xml L1-40 (config_block, score=1.8704, sources=['bm25'])
  - [2] src/main/java/com/springfix/sample/transaction/Application.java L13-16 (method, score=0.5437, sources=['bm25'])
  - [3] pom.xml L36-49 (config_block, score=0.4718, sources=['bm25'])
  - [4] src/main/java/com/springfix/sample/transaction/service/OrderService.java L28-34 (method, score=0.4168, sources=['bm25'])
- **symbol**: activated=False, hits=0, input=[]
  - first_relevant_rank: -1
- **hybrid**: R@1=0.00 R@3=1.00 R@5=1.00 MRR=0.50 (9.726ms, 5 hits)
  - symbol_activated=False, symbol_hits=0
  - first_relevant_rank: 1
  - [0] pom.xml L1-40 (config_block, score=0.0164, sources=['baseline', 'bm25'])
  - [1] src/main/resources/application.properties L1-6 (config_block, score=0.0164, sources=['bm25', 'baseline'])
  - [2] src/main/java/com/springfix/sample/transaction/Application.java L13-16 (method, score=0.0159, sources=['bm25'])
  - [3] src/main/java/com/springfix/sample/transaction/service/OrderService.java L1-6 (file_window, score=0.0159, sources=['baseline'])
  - [4] pom.xml L36-49 (config_block, score=0.0156, sources=['bm25'])

### retrieval-sql-repository (development)

- query_terms: ['create', 'table', 'orders', 'insert', 'jdbc', 'template', 'sql', 'update', 'order', 'in']
- exact_symbols: ['JdbcTemplate', 'createOrderInTransaction']

- **baseline**: R@1=0.50 R@3=0.50 R@5=0.50 MRR=1.00 (3.000ms, 2 hits)
  - first_relevant_rank: 0
  - [0] src/main/java/com/springfix/sample/transaction/service/OrderService.java L4-39 (file_window, score=11.0000, sources=['baseline'])
  - [1] src/test/java/com/springfix/sample/transaction/TransactionSelfInvocationTest.java L7-37 (file_window, score=6.0000, sources=['baseline'])
- **bm25**: R@1=0.50 R@3=1.00 R@5=1.00 MRR=1.00 (0.218ms, 5 hits)
  - first_relevant_rank: 0
  - [0] src/main/java/com/springfix/sample/transaction/service/OrderService.java L35-43 (method, score=4.8298, sources=['bm25'])
  - [1] src/main/resources/schema.sql L1-5 (file_window, score=3.2505, sources=['bm25'])
  - [2] src/main/java/com/springfix/sample/transaction/service/OrderService.java L9-44 (class, score=2.9584, sources=['bm25'])
  - [3] src/main/resources/application.properties L1-6 (config_block, score=2.7834, sources=['bm25'])
  - [4] src/test/java/com/springfix/sample/transaction/TransactionSelfInvocationTest.java L29-48 (method, score=1.7568, sources=['bm25'])
- **symbol**: activated=True, hits=1, input=['JdbcTemplate', 'createOrderInTransaction']
  - first_relevant_rank: 0
  - [0] src/main/java/com/springfix/sample/transaction/service/OrderService.java L37-43 (method, score=0.0000, sources=['symbol'])
- **hybrid**: R@1=0.50 R@3=1.00 R@5=1.00 MRR=1.00 (17.533ms, 5 hits)
  - symbol_activated=True, symbol_hits=1
  - first_relevant_rank: 0
  - [0] src/main/java/com/springfix/sample/transaction/service/OrderService.java L9-44 (class, score=0.0246, sources=['symbol', 'bm25'])
  - [1] src/main/java/com/springfix/sample/transaction/service/OrderService.java L1-39 (file_window, score=0.0164, sources=['baseline'])
  - [2] src/main/resources/schema.sql L1-5 (file_window, score=0.0161, sources=['bm25'])
  - [3] src/test/java/com/springfix/sample/transaction/TransactionSelfInvocationTest.java L1-46 (file_window, score=0.0161, sources=['baseline', 'bm25'])
  - [4] pom.xml L1-47 (file_window, score=0.0159, sources=['baseline'])

### retrieval-cache (development)

- query_terms: ['cacheable', 'cache', 'evict', 'manager', 'miss', 'self', 'invocation', 'proxy', 'bypass', 'user']
- exact_symbols: ['UserCacheService', 'getUserById', 'Cacheable']

- **baseline**: R@1=1.00 R@3=1.00 R@5=1.00 MRR=1.00 (0.000ms, 1 hits)
  - first_relevant_rank: 0
  - [0] UserCacheService.java L3-22 (file_window, score=16.0000, sources=['baseline'])
- **bm25**: R@1=1.00 R@3=1.00 R@5=1.00 MRR=1.00 (0.118ms, 3 hits)
  - first_relevant_rank: 0
  - [0] UserCacheService.java L7-30 (class, score=1.1074, sources=['bm25'])
  - [1] UserCacheService.java L16-20 (method, score=1.0824, sources=['bm25'])
  - [2] UserCacheService.java L12-15 (constructor, score=0.5255, sources=['bm25'])
- **symbol**: activated=True, hits=3, input=['UserCacheService', 'getUserById', 'Cacheable']
  - first_relevant_rank: 0
  - [0] UserCacheService.java L9-30 (class, score=0.0000, sources=['symbol'])
  - [1] UserCacheService.java L18-20 (method, score=0.0000, sources=['symbol'])
  - [2] UserCacheService.java L17-30 (annotation_block, score=0.0000, sources=['symbol'])
- **hybrid**: R@1=1.00 R@3=1.00 R@5=1.00 MRR=1.00 (2.599ms, 1 hits)
  - symbol_activated=True, symbol_hits=3
  - first_relevant_rank: 0
  - [0] UserCacheService.java L1-28 (file_window, score=0.0246, sources=['symbol', 'baseline', 'bm25'])

### retrieval-concurrency (development)

- query_terms: ['reentrant', 'lock', 'synchronized', 'thread', 'safety', 'stock', 'race', 'condition', 'inventory', 'service']
- exact_symbols: ['InventoryService', 'reduceStock']

- **baseline**: R@1=1.00 R@3=1.00 R@5=1.00 MRR=1.00 (0.000ms, 1 hits)
  - first_relevant_rank: 0
  - [0] InventoryService.java L3-24 (file_window, score=10.0000, sources=['baseline'])
- **bm25**: R@1=1.00 R@3=1.00 R@5=1.00 MRR=1.00 (0.097ms, 1 hits)
  - first_relevant_rank: 0
  - [0] InventoryService.java L4-26 (class, score=0.8944, sources=['bm25'])
- **symbol**: activated=True, hits=2, input=['InventoryService', 'reduceStock']
  - first_relevant_rank: 0
  - [0] InventoryService.java L4-26 (class, score=0.0000, sources=['symbol'])
  - [1] InventoryService.java L9-21 (method, score=0.0000, sources=['symbol'])
- **hybrid**: R@1=1.00 R@3=1.00 R@5=1.00 MRR=1.00 (2.164ms, 1 hits)
  - symbol_activated=True, symbol_hits=2
  - first_relevant_rank: 0
  - [0] InventoryService.java L4-26 (class, score=0.0410, sources=['bm25', 'symbol', 'baseline'])

### retrieval-exact-method-createOrder (development)

- query_terms: ['create', 'order']
- exact_symbols: ['createOrder']

- **baseline**: R@1=1.00 R@3=1.00 R@5=1.00 MRR=1.00 (3.000ms, 2 hits)
  - first_relevant_rank: 0
  - [0] src/main/java/com/springfix/sample/transaction/service/OrderService.java L11-37 (file_window, score=10.0000, sources=['baseline'])
  - [1] src/test/java/com/springfix/sample/transaction/TransactionSelfInvocationTest.java L14-34 (file_window, score=6.0000, sources=['baseline'])
- **bm25**: R@1=0.00 R@3=0.00 R@5=0.00 MRR=0.00 (0.050ms, 0 hits)
  - first_relevant_rank: -1
- **symbol**: activated=True, hits=1, input=['createOrder']
  - first_relevant_rank: 0
  - [0] src/main/java/com/springfix/sample/transaction/service/OrderService.java L31-34 (method, score=0.0000, sources=['symbol'])
- **hybrid**: R@1=1.00 R@3=1.00 R@5=1.00 MRR=1.00 (12.336ms, 2 hits)
  - symbol_activated=True, symbol_hits=1
  - first_relevant_rank: 0
  - [0] src/main/java/com/springfix/sample/transaction/service/OrderService.java L11-39 (file_window, score=0.0246, sources=['symbol', 'baseline'])
  - [1] src/test/java/com/springfix/sample/transaction/TransactionSelfInvocationTest.java L14-37 (file_window, score=0.0164, sources=['baseline'])

### retrieval-exception-class (holdout)

- query_terms: ['runtime', 'exception', 'rollback', 'self', 'invocation', 'create', 'order', 'in', 'transaction']
- exact_symbols: ['RuntimeException', 'createOrderInTransaction']

- **baseline**: R@1=1.00 R@3=1.00 R@5=1.00 MRR=1.00 (4.000ms, 4 hits)
  - first_relevant_rank: 0
  - [0] src/main/java/com/springfix/sample/transaction/service/OrderService.java L9-42 (file_window, score=9.0000, sources=['baseline'])
  - [1] src/test/java/com/springfix/sample/transaction/TransactionSelfInvocationTest.java L13-46 (file_window, score=7.0000, sources=['baseline'])
  - [2] pom.xml L15-18 (file_window, score=3.0000, sources=['baseline'])
  - [3] src/main/java/com/springfix/sample/transaction/Application.java L7-7 (file_window, score=1.0000, sources=['baseline'])
- **bm25**: R@1=1.00 R@3=1.00 R@5=1.00 MRR=1.00 (0.143ms, 5 hits)
  - first_relevant_rank: 0
  - [0] src/main/java/com/springfix/sample/transaction/service/OrderService.java L35-43 (method, score=3.2141, sources=['bm25'])
  - [1] src/main/java/com/springfix/sample/transaction/service/OrderService.java L9-44 (class, score=1.9687, sources=['bm25'])
  - [2] src/test/java/com/springfix/sample/transaction/TransactionSelfInvocationTest.java L29-48 (method, score=1.7112, sources=['bm25'])
  - [3] src/main/java/com/springfix/sample/transaction/service/OrderService.java L28-34 (method, score=1.5173, sources=['bm25'])
  - [4] src/test/java/com/springfix/sample/transaction/TransactionSelfInvocationTest.java L13-49 (class, score=1.2493, sources=['bm25'])
- **symbol**: activated=True, hits=1, input=['RuntimeException', 'createOrderInTransaction']
  - first_relevant_rank: 0
  - [0] src/main/java/com/springfix/sample/transaction/service/OrderService.java L37-43 (method, score=0.0000, sources=['symbol'])
- **hybrid**: R@1=1.00 R@3=1.00 R@5=1.00 MRR=1.00 (17.465ms, 5 hits)
  - symbol_activated=True, symbol_hits=1
  - first_relevant_rank: 0
  - [0] src/main/java/com/springfix/sample/transaction/service/OrderService.java L1-42 (file_window, score=0.0246, sources=['symbol', 'bm25', 'baseline'])
  - [1] src/test/java/com/springfix/sample/transaction/TransactionSelfInvocationTest.java L1-46 (file_window, score=0.0164, sources=['baseline', 'bm25'])
  - [2] pom.xml L1-47 (file_window, score=0.0159, sources=['baseline'])
  - [3] src/main/java/com/springfix/sample/transaction/Application.java L1-15 (file_window, score=0.0156, sources=['baseline'])
  - [4] src/main/resources/application.properties L1-6 (file_window, score=0.0154, sources=['baseline'])

### retrieval-exact-class-OrderService (holdout)

- query_terms: ['order', 'service', 'class', 'declaration']
- exact_symbols: ['OrderService']

- **baseline**: R@1=0.00 R@3=1.00 R@5=1.00 MRR=0.50 (4.000ms, 4 hits)
  - first_relevant_rank: 1
  - [0] src/test/java/com/springfix/sample/transaction/TransactionSelfInvocationTest.java L3-38 (file_window, score=9.0000, sources=['baseline'])
  - [1] src/main/java/com/springfix/sample/transaction/service/OrderService.java L9-23 (file_window, score=7.0000, sources=['baseline'])
  - [2] src/main/java/com/springfix/sample/transaction/Application.java L12-15 (file_window, score=2.0000, sources=['baseline'])
  - [3] src/main/resources/application.properties L2-6 (file_window, score=2.0000, sources=['baseline'])
- **bm25**: R@1=1.00 R@3=1.00 R@5=1.00 MRR=1.00 (0.105ms, 4 hits)
  - first_relevant_rank: 0
  - [0] src/main/java/com/springfix/sample/transaction/service/OrderService.java L21-25 (constructor, score=0.9697, sources=['bm25'])
  - [1] src/test/java/com/springfix/sample/transaction/TransactionSelfInvocationTest.java L29-48 (method, score=0.5552, sources=['bm25'])
  - [2] src/main/java/com/springfix/sample/transaction/service/OrderService.java L9-44 (class, score=0.4232, sources=['bm25'])
  - [3] src/test/java/com/springfix/sample/transaction/TransactionSelfInvocationTest.java L13-49 (class, score=0.4053, sources=['bm25'])
- **symbol**: activated=True, hits=1, input=['OrderService']
  - first_relevant_rank: 0
  - [0] src/main/java/com/springfix/sample/transaction/service/OrderService.java L18-44 (class, score=0.0000, sources=['symbol'])
- **hybrid**: R@1=1.00 R@3=1.00 R@5=1.00 MRR=1.00 (13.718ms, 4 hits)
  - symbol_activated=True, symbol_hits=1
  - first_relevant_rank: 0
  - [0] src/main/java/com/springfix/sample/transaction/service/OrderService.java L1-39 (file_window, score=0.0246, sources=['symbol', 'bm25', 'baseline'])
  - [1] src/test/java/com/springfix/sample/transaction/TransactionSelfInvocationTest.java L13-49 (class, score=0.0164, sources=['baseline', 'bm25'])
  - [2] src/main/java/com/springfix/sample/transaction/Application.java L12-15 (file_window, score=0.0159, sources=['baseline'])
  - [3] src/main/resources/application.properties L2-6 (file_window, score=0.0156, sources=['baseline'])

### retrieval-spring-application (holdout)

- query_terms: ['spring', 'boot', 'application', 'main', 'entry', 'point']
- exact_symbols: []

- **baseline**: R@1=1.00 R@3=1.00 R@5=1.00 MRR=1.00 (3.000ms, 2 hits)
  - first_relevant_rank: 0
  - [0] src/main/java/com/springfix/sample/transaction/Application.java L4-14 (file_window, score=8.0000, sources=['baseline'])
  - [1] src/main/java/com/springfix/sample/transaction/service/OrderService.java L11-28 (file_window, score=4.0000, sources=['baseline'])
- **bm25**: R@1=1.00 R@3=1.00 R@5=1.00 MRR=1.00 (0.112ms, 5 hits)
  - first_relevant_rank: 0
  - [0] src/main/java/com/springfix/sample/transaction/Application.java L13-16 (method, score=4.6699, sources=['bm25'])
  - [1] src/main/java/com/springfix/sample/transaction/Application.java L7-17 (class, score=4.2194, sources=['bm25'])
  - [2] src/main/java/com/springfix/sample/transaction/service/OrderService.java L28-34 (method, score=3.5800, sources=['bm25'])
  - [3] src/main/java/com/springfix/sample/transaction/service/OrderService.java L9-44 (class, score=2.1613, sources=['bm25'])
  - [4] pom.xml L36-49 (config_block, score=1.2654, sources=['bm25'])
- **symbol**: activated=False, hits=0, input=[]
  - first_relevant_rank: -1
- **hybrid**: R@1=0.00 R@3=1.00 R@5=1.00 MRR=0.50 (10.754ms, 5 hits)
  - symbol_activated=False, symbol_hits=0
  - first_relevant_rank: 1
  - [0] pom.xml L8-45 (file_window, score=0.0164, sources=['baseline', 'bm25'])
  - [1] src/main/java/com/springfix/sample/transaction/Application.java L1-14 (file_window, score=0.0164, sources=['bm25', 'baseline'])
  - [2] src/main/java/com/springfix/sample/transaction/service/OrderService.java L9-44 (class, score=0.0159, sources=['baseline', 'bm25'])
  - [3] src/main/java/com/springfix/sample/transaction/service/OrderService.java L28-34 (method, score=0.0159, sources=['bm25'])
  - [4] src/main/resources/application.properties L1-6 (file_window, score=0.0156, sources=['baseline'])

### retrieval-jdbc-sql-operations (holdout)

- query_terms: ['jdbc', 'template', 'update', 'insert', 'sql', 'query', 'execution']
- exact_symbols: ['JdbcTemplate']

- **baseline**: R@1=1.00 R@3=1.00 R@5=1.00 MRR=1.00 (4.000ms, 2 hits)
  - first_relevant_rank: 0
  - [0] src/main/java/com/springfix/sample/transaction/service/OrderService.java L4-39 (file_window, score=9.0000, sources=['baseline'])
  - [1] src/test/java/com/springfix/sample/transaction/TransactionSelfInvocationTest.java L7-36 (file_window, score=5.0000, sources=['baseline'])
- **bm25**: R@1=1.00 R@3=1.00 R@5=1.00 MRR=1.00 (0.130ms, 5 hits)
  - first_relevant_rank: 0
  - [0] src/main/java/com/springfix/sample/transaction/service/OrderService.java L35-43 (method, score=2.9974, sources=['bm25'])
  - [1] src/main/resources/application.properties L1-6 (config_block, score=2.7834, sources=['bm25'])
  - [2] src/test/java/com/springfix/sample/transaction/TransactionSelfInvocationTest.java L29-48 (method, score=2.4087, sources=['bm25'])
  - [3] src/main/java/com/springfix/sample/transaction/service/OrderService.java L9-44 (class, score=1.8360, sources=['bm25'])
  - [4] src/test/java/com/springfix/sample/transaction/TransactionSelfInvocationTest.java L13-49 (class, score=1.7586, sources=['bm25'])
- **symbol**: activated=True, hits=0, input=['JdbcTemplate']
  - first_relevant_rank: -1
- **hybrid**: R@1=1.00 R@3=1.00 R@5=1.00 MRR=1.00 (14.189ms, 5 hits)
  - symbol_activated=True, symbol_hits=0
  - first_relevant_rank: 0
  - [0] src/main/java/com/springfix/sample/transaction/service/OrderService.java L9-44 (class, score=0.0164, sources=['baseline', 'bm25'])
  - [1] src/main/java/com/springfix/sample/transaction/service/OrderService.java L35-43 (method, score=0.0164, sources=['bm25'])
  - [2] src/main/resources/application.properties L1-6 (config_block, score=0.0161, sources=['bm25', 'baseline'])
  - [3] src/test/java/com/springfix/sample/transaction/TransactionSelfInvocationTest.java L13-49 (class, score=0.0161, sources=['baseline', 'bm25'])
  - [4] pom.xml L27-27 (file_window, score=0.0156, sources=['baseline'])

### retrieval-service-stereotype (holdout)

- query_terms: ['service', 'stereotype', 'annotation', 'spring', 'bean', 'registration']
- exact_symbols: []

- **baseline**: R@1=1.00 R@3=1.00 R@5=1.00 MRR=1.00 (4.000ms, 4 hits)
  - first_relevant_rank: 0
  - [0] src/main/java/com/springfix/sample/transaction/service/OrderService.java L3-32 (file_window, score=20.5000, sources=['baseline'])
  - [1] src/test/java/com/springfix/sample/transaction/TransactionSelfInvocationTest.java L3-34 (file_window, score=16.0000, sources=['baseline'])
  - [2] src/main/java/com/springfix/sample/transaction/Application.java L3-15 (file_window, score=12.0000, sources=['baseline'])
  - [3] pom.xml L18-18 (file_window, score=2.0000, sources=['baseline'])
- **bm25**: R@1=1.00 R@3=1.00 R@5=1.00 MRR=1.00 (0.183ms, 5 hits)
  - first_relevant_rank: 0
  - [0] src/main/java/com/springfix/sample/transaction/service/OrderService.java L21-25 (constructor, score=0.9697, sources=['bm25'])
  - [1] src/main/java/com/springfix/sample/transaction/service/OrderService.java L9-44 (class, score=0.6748, sources=['bm25'])
  - [2] src/test/java/com/springfix/sample/transaction/TransactionSelfInvocationTest.java L13-49 (class, score=0.6463, sources=['bm25'])
  - [3] src/test/java/com/springfix/sample/transaction/TransactionSelfInvocationTest.java L29-48 (method, score=0.5552, sources=['bm25'])
  - [4] src/main/java/com/springfix/sample/transaction/Application.java L13-16 (method, score=0.5437, sources=['bm25'])
- **symbol**: activated=False, hits=0, input=[]
  - first_relevant_rank: -1
- **hybrid**: R@1=1.00 R@3=1.00 R@5=1.00 MRR=1.00 (11.317ms, 5 hits)
  - symbol_activated=False, symbol_hits=0
  - first_relevant_rank: 0
  - [0] src/main/java/com/springfix/sample/transaction/service/OrderService.java L1-6 (file_window, score=0.0164, sources=['baseline'])
  - [1] src/main/java/com/springfix/sample/transaction/service/OrderService.java L9-44 (class, score=0.0164, sources=['bm25'])
  - [2] pom.xml L8-45 (file_window, score=0.0161, sources=['baseline'])
  - [3] src/test/java/com/springfix/sample/transaction/TransactionSelfInvocationTest.java L1-7 (file_window, score=0.0159, sources=['baseline'])
  - [4] src/test/java/com/springfix/sample/transaction/TransactionSelfInvocationTest.java L13-49 (class, score=0.0159, sources=['bm25'])

### retrieval-test-assertion-failure (holdout)

- query_terms: ['assert', 'equals', 'assertion', 'failure', 'rollback', 'expected', 'actual', 'count', 'test', 'verification']
- exact_symbols: ['TransactionSelfInvocationTest', 'shouldRollbackOrderWhenInnerMethodThrows', 'AssertionFailedError']

- **baseline**: R@1=1.00 R@3=1.00 R@5=1.00 MRR=1.00 (3.000ms, 2 hits)
  - first_relevant_rank: 0
  - [0] src/test/java/com/springfix/sample/transaction/TransactionSelfInvocationTest.java L9-45 (file_window, score=11.0000, sources=['baseline'])
  - [1] src/main/java/com/springfix/sample/transaction/service/OrderService.java L42-42 (file_window, score=2.0000, sources=['baseline'])
- **bm25**: R@1=1.00 R@3=1.00 R@5=1.00 MRR=1.00 (0.219ms, 5 hits)
  - first_relevant_rank: 0
  - [0] src/test/java/com/springfix/sample/transaction/TransactionSelfInvocationTest.java L29-48 (method, score=10.4155, sources=['bm25'])
  - [1] src/test/java/com/springfix/sample/transaction/TransactionSelfInvocationTest.java L13-49 (class, score=9.5387, sources=['bm25'])
  - [2] src/main/java/com/springfix/sample/transaction/service/OrderService.java L9-44 (class, score=2.6679, sources=['bm25'])
  - [3] src/main/java/com/springfix/sample/transaction/service/OrderService.java L35-43 (method, score=2.1863, sources=['bm25'])
  - [4] src/main/java/com/springfix/sample/transaction/Application.java L7-17 (class, score=0.7477, sources=['bm25'])
- **symbol**: activated=True, hits=2, input=['TransactionSelfInvocationTest', 'shouldRollbackOrderWhenInnerMethodThrows', 'AssertionFailedError']
  - first_relevant_rank: 0
  - [0] src/test/java/com/springfix/sample/transaction/TransactionSelfInvocationTest.java L22-49 (class, score=0.0000, sources=['symbol'])
  - [1] src/test/java/com/springfix/sample/transaction/TransactionSelfInvocationTest.java L31-48 (method, score=0.0000, sources=['symbol'])
- **hybrid**: R@1=1.00 R@3=1.00 R@5=1.00 MRR=1.00 (20.148ms, 5 hits)
  - symbol_activated=True, symbol_hits=2
  - first_relevant_rank: 0
  - [0] src/test/java/com/springfix/sample/transaction/TransactionSelfInvocationTest.java L1-46 (file_window, score=0.0246, sources=['symbol', 'baseline', 'bm25'])
  - [1] src/main/java/com/springfix/sample/transaction/service/OrderService.java L1-42 (file_window, score=0.0161, sources=['baseline', 'bm25'])
  - [2] pom.xml L15-37 (file_window, score=0.0159, sources=['baseline'])
  - [3] src/main/java/com/springfix/sample/transaction/Application.java L1-9 (file_window, score=0.0156, sources=['baseline'])
  - [4] src/main/java/com/springfix/sample/transaction/Application.java L7-17 (class, score=0.0154, sources=['bm25'])

---

## Notes

- BM25 is **lexical (keyword) retrieval**, not semantic search.
- Hybrid improves Top-K recall completeness; Top-1 improvement depends on holdout data.
- Symbol channel is activated by `issue_analysis.extracted_symbols` from the query builder, NOT by expected_symbols (gold standard).
- Retrieval benchmark does NOT measure Agent root-cause accuracy.
- Development data used for parameter selection; holdout data used for limited validation only.
- Sample size is small; P95 values are indicative, not production performance claims.
- * = small sample (<10 cases), P95 is indicative only.