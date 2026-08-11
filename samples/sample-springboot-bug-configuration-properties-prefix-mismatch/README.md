# ConfigurationProperties Prefix Mismatch

## 1. Bug name

`@ConfigurationProperties` prefix mismatch.

## 2. Scenario

`MailProperties` is registered with the prefix `springfix.mail`, and a mail
service consumes its `timeoutSeconds` value.

## 3. User-observed symptom

The application starts, but the configured timeout is not bound and remains
zero.

## 4. Expected behaviour

`MailProperties.timeoutSeconds` should be `30`.

## 5. Actual behaviour

The intentional assertion reports `expected: <30> but was: <0>`.

## 6. Root cause

The YAML uses `springfix.email.timeout-seconds`, while the class declares the
prefix `springfix.mail`.

## 7. Key files

- `MailProperties.java`
- `MailService.java`
- `application.yml`

## 8. Key symbols

`MailProperties`, `timeoutSeconds`, `MailService`, and
`shouldBindConfiguredMailTimeout`.

## 9. Maven reproduction

```bash
mvn test
```

## 10. Expected test result

Surefire must report one test, one assertion failure, zero errors, and zero
skipped tests.

## 11. Suggested repair

Change `springfix.email` to `springfix.mail`, or change the annotation prefix
to match the intended configuration namespace.

## 12. Why this remains a benchmark

The failing assertion is intentional benchmark gold. The sample remains
unrepaired so an agent can diagnose the mismatch from source and configuration.
