# NoUniqueBeanDefinition

## 1. Bug name

`NoUniqueBeanDefinitionException` caused by ambiguous constructor injection.

## 2. Scenario

The application defines two `PaymentGateway` components, Stripe and Paypal.
`CheckoutService` injects the interface directly.

## 3. User-observed symptom

The application context does not start because Spring cannot choose a single
`PaymentGateway` bean.

## 4. Expected behaviour

The context should start with one explicitly selected gateway.

## 5. Actual behaviour

The context startup failure is captured by `ApplicationContextRunner`, and the
intentional assertion fails with a `NoUniqueBeanDefinitionException` cause.

## 6. Root cause

Both `StripePaymentGateway` and `PaypalPaymentGateway` are candidates, while
the constructor has no `@Qualifier` and neither bean is `@Primary`.

## 7. Key files

- `PaymentGateway.java`
- `StripePaymentGateway.java`
- `PaypalPaymentGateway.java`
- `CheckoutService.java`

## 8. Key symbols

`PaymentGateway`, `StripePaymentGateway`, `PaypalPaymentGateway`,
`CheckoutService`, and `contextShouldStartWithSinglePaymentGateway`.

## 9. Maven reproduction

```bash
mvn test
```

## 10. Expected test result

Surefire must report one test, one assertion failure, zero errors, and zero
skipped tests.

## 11. Suggested repair

Use `@Qualifier`, `@Primary`, or another explicit bean-selection mechanism.

## 12. Why this remains a benchmark

The failing test is intentional benchmark gold. The source must remain
unrepaired so an agent can diagnose the ambiguity from code and logs.
