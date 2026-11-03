"""Invoke dcode; the external CLI owns its agents, tools and contexts."""

from dataclasses import dataclass
import json

from .._cli import run_cli

VERSION = "0.2.2"
SDK_VERSION = "0.7.32"


@dataclass(frozen=True)
class DeepAgentsCLI:
    executable: str = "dcode"

    def command(self, model, *, shell_allow_list=None, model_params=None,
                summarization_model=None, profile_override=None, no_mcp=False, single_agent=False,
                max_turns=None):
        if not model.strip() or model.startswith("-"):
            raise ValueError("An explicit model is required")
        args = [str(self.executable), "--stdin", "--quiet", "--no-stream",
                "--model", model, "--max-retries", "0"]
        if shell_allow_list is not None:
            if not shell_allow_list.strip() or shell_allow_list.startswith("-"):
                raise ValueError("Shell allow-list must not be empty or an option")
            args.extend(["--shell-allow-list", shell_allow_list])
        if model_params is not None:
            args.extend(["--model-params", json.dumps(model_params, allow_nan=False)])
        if profile_override is not None:
            args.extend(["--profile-override", json.dumps(profile_override, allow_nan=False)])
        if summarization_model is not None:
            args.extend(["--summarization-model", summarization_model])
        if no_mcp or single_agent:
            args.append("--no-mcp")
        if single_agent:
            args.append("--no-interpreter")
        if max_turns is not None:
            if type(max_turns) is not int or max_turns < 1:
                raise ValueError("max_turns must be a positive integer")
            args.extend(["--max-turns", str(max_turns)])
        return args

    def run(self, prompt, *, model, workspace, output, timeout=3600,
            shell_allow_list=None, execute=False, command_prefix=(), model_params=None,
            summarization_model=None, profile_override=None, no_mcp=False, single_agent=False,
            policy_profile=None, profile_target=None, max_turns=None):
        environment = {"DEEPAGENTS_CODE_AUTO_UPDATE": "0",
                       "DEEPAGENTS_CODE_NO_UPDATE_CHECK": "1",
                       "DEEPAGENTS_CODE_PLUGIN_AUTO_UPDATE": "0",
                       "DEEPAGENTS_CODE_PRICES_AUTO_UPDATE": "0",
                       "LANGSMITH_TRACING": "false", "LANGCHAIN_TRACING_V2": "false"}
        if single_agent:
            from .single import validate_profile
            if policy_profile is None:
                raise ValueError("Single-agent mode requires a prepared native policy profile")
            if execute:
                validate_profile(policy_profile)
            environment.update(DEEPAGENTS_HOME=str(profile_target or policy_profile),
                               DEEPAGENTS_CODE_EXTENSIONS="0", DEEPAGENTS_CODE_EXPERIMENTAL="0")
        return run_cli(
            backend="deepagents", argv=self.command(model, shell_allow_list=shell_allow_list,
                model_params=model_params, summarization_model=summarization_model,
                profile_override=profile_override, no_mcp=no_mcp, single_agent=single_agent, max_turns=max_turns),
            version=VERSION, version_pattern=r"^deepagents-code (\d+\.\d+\.\d+)(?:\s|$)",
            environment=environment,
            prompt=prompt, workspace=workspace, output=output, timeout=timeout, execute=execute,
            command_prefix=command_prefix)
