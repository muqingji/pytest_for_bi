"""Domain errors with stable reason codes for workflow routing."""


class QaAgentError(Exception):
    reason_code = "qa_agent_error"
    retryable = False


class ContractError(QaAgentError):
    reason_code = "contract_validation_failed"


class InputError(QaAgentError):
    reason_code = "blocked_input"


class SecurityPolicyError(QaAgentError):
    reason_code = "security_policy_violation"


class RetryableAgentError(QaAgentError):
    reason_code = "agent_runtime_error"
    retryable = True
