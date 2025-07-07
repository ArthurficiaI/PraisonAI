import dotenv
from dotenv import load_dotenv
load_dotenv()
import asyncio
import json
import re
import requests
import subprocess

import os
import openai

from config import *
import litellm
print(litellm._turn_on_debug())
#http://188.245.32.59:4000
#http://localhost:11434/
from praisonaiagents import Agent, Task, PraisonAIAgents
#from app.config import config
from praisonaiagents.tools import read_file, write_file, list_files, get_file_info, copy_file, move_file, delete_file, calculator_tools
from praisonaiagents.tools import (
    evaluate, solve_equation, convert_units,
    calculate_statistics, calculate_financial
)
from praisonaiagents.tools import (
    execute_code, analyze_code, format_code,
    lint_code, disassemble_code
)


API_URL = "http://localhost:8081/task/index/"  # API endpoint for SWE-Bench-Lite
LOG_FILE = "results.log"

async def handle_task(index):
    print(os.getenv("OPEN_API_KEY"))


    api_url = f"{API_URL}{index}"
    print(f"Fetching test case {index} from {api_url}...")
    root_dir = os.path.dirname(os.path.abspath(__file__))
    repo_dir = os.path.join(root_dir, f"repo_{index}")  # Use unique repo directory per task
    start_dir = os.getcwd()  # Remember original working directory

    try:
        response = requests.get(api_url)
        if response.status_code != 200:
            raise Exception(f"Invalid response: {response.status_code}")

        testcase = response.json()
        prompt = testcase["Problem_statement"]
        git_clone = testcase["git_clone"]
        fail_tests = json.loads(testcase.get("FAIL_TO_PASS", "[]"))
        pass_tests = json.loads(testcase.get("PASS_TO_PASS", "[]"))
        instance_id = testcase["instance_id"]

        # Extract repo URL and commit hash
        parts = git_clone.split("&&")
        clone_part = parts[0].strip()
        checkout_part = parts[-1].strip() if len(parts) > 1 else None

        repo_url = clone_part.split()[2]

        print(f"Cloning repository {repo_url} into {repo_dir}...")
        env = os.environ.copy()
        env["GIT_TERMINAL_PROMPT"] = "0"

        if not os.path.isdir(repo_dir):
            subprocess.run(["git", "clone", repo_url, repo_dir], check=True, env=env)

            if checkout_part:
                commit_hash = checkout_part.split()[-1]
                print(f"Checking out commit: {commit_hash}")
                subprocess.run(["git", "checkout", commit_hash], cwd=repo_dir, check=True, env=env)





        planning_Agent = Agent(
            name="Planner",
            backstory="You are a senior software architect, leading a team of professionals.",
            goal= "Research the code in a given repository together with a given issue.\n"
                  "Break the problem down into coding tasks for your team members.\n"
                  "Make sure the fix is minimal and only touches what's necessary to resolve the failing tests\n"
                  "You have a highly capable Tester and Coder at your disposal.\n"
                  "Always tell them the corresponding file paths to their tasks.",
            verbose=True,

            tools=[read_file, list_files, get_file_info, execute_code, analyze_code, format_code, lint_code, disassemble_code],
            allow_delegation=True,
            self_reflect=True,
            min_reflect=2,
            max_reflect=4,
            instructions=f"Do this task with your team of two other agents with the following roles:\n"
            f"Always research into the given repository and find out what the problem is, before concluding.\n"
            f"- Coder: makes actual changes to the code files in the Git repository\n"
            f"- Tester: runs the test suite and checks whether the bug is resolved\n\n"
            f"Work in the directory: repo_{index}. This is a Git repository.\n"
            f"Your goal is to fix the problem described below.\n"
            f"All code changes must be saved to the files, so they appear in `git diff`.\n"
            f"The fix will be verified by running the affected tests.\n"
            f"Problem description:\n\n"
            f"{prompt}\n\n"
            f"Make sure the fix is minimal and only touches what's necessary to resolve the failing tests.\n"
            f"Your job is only done after the issue has been fixed, or you tried for long enough\n"
            f"Give the coder and tester agents instructions, after you have developed a plan. ALWAYS give them all relevant paths for their tasks."
        )

        coding_Agent = Agent(
            name="Coder",
            backstory="You are a senior software developer, having specialized in fixing special problems in repositiories.",
            goal="Resolve the coding tasks given to you by the Planner.\n"
                 "Write the fixes directly into the files, that you are supposed to repair.\n"
                 "Make sure the fix is minimal and only touches what's necessary to resolve the failing tests",
            verbose=True,
            self_reflect=True,
            tools=[read_file, write_file, list_files, get_file_info, copy_file, move_file, delete_file,execute_code, analyze_code, format_code,lint_code, disassemble_code],
            allow_code_execution=True,
            instructions=f"Follow the given coding instructions by Planner\n"
                        f"fWork in the directory: repo_{index}. This is a Git repository.\n"
                        f"Your goal is to fix the problem described below.\n"
                        f"All code changes must be saved to the files, so they appear in `git diff`.\n"
                        f"The fix will be verified by running the affected tests.\n"
                        f"Make sure the fix is minimal and only touches what's necessary to resolve the failing tests. Tell the planner when you think you're done coding.",
        )

        testing_Agent = Agent(
            name="Tester",
            backstory="You are a senior software developer, having specialized in testing.\n",
            goal="Run the testsuite in the repository.\n"
                 "Communicate to Planner exactly which tests failed.",
            verbose=True,
            tools=[read_file,list_files, get_file_info, execute_code, analyze_code, format_code, lint_code, disassemble_code],
            allow_code_execution=True,
            instructions=f"Follow the given coding instructions by Planner\n"
                        f"fWork in the directory: repo_{index}. This is a Git repository.\n"
                        f"Your goal is to run the tests in the repo and to either confirm or deny the correctness of the fixes by coder.\n"
                        f"You report to Planner, who will then resume the work or break the task off, if the tests run good enough.\n"
                        f"The fix will be verified by running the affected tests.\n",
            self_reflect=True

        )



        print(f"Launching agents (PraisonAI)...")


        # task = Task(
        #     name="Fixing_issue_in_repo_task",
        #     description=f"Do this task with your team of two other agents with the following roles:\n"
        #     f"Always research into the given repository and find out what the problem is, before concluding.\n"
        #     f"- Coder: makes actual changes to the code files in the Git repository\n"
        #     f"- Tester: runs the test suite and checks whether the bug is resolved\n\n"
        #     f"Work in the directory: repo_{index}. This is a Git repository.\n"
        #     f"Your goal is to fix the problem described below.\n"
        #     f"All code changes must be saved to the files, so they appear in `git diff`.\n"
        #     f"The fix will be verified by running the affected tests.\n"
        #     f"Problem description:\n\n"
        #     f"{prompt}\n\n"
        #     f"Make sure the fix is minimal and only touches what's necessary to resolve the failing tests.\n"
        #     f"Your job is only done after the issue has been fixed, or you tried for long enough",
        #     agent=planning_Agent
        # )
        #
        # coding_task = Task(
        #     name="coding_task",
        #     description=f"Follow the given coding instructions by Planner\n"
        #                 f"fWork in the directory: repo_{index}. This is a Git repository.\n"
        #     f"Your goal is to fix the problem described below.\n"
        #     f"All code changes must be saved to the files, so they appear in `git diff`.\n"
        #     f"The fix will be verified by running the affected tests.\n"
        #     f"Make sure the fix is minimal and only touches what's necessary to resolve the failing tests.",
        #     expected_output="Correct files",
        #     agent=coding_Agent,
        #
        # )
        #
        # testing_task = Task(
        #     name="testing_task",
        #     description=f"Follow the given coding instructions by Planner\n"
        #                 f"fWork in the directory: repo_{index}. This is a Git repository.\n"
        #     f"Your goal is to run the tests in the repo and to either confirm or deny the correctness of the fixes by coder.\n"
        #     f"You report to Planner, who will then resume the work or break the task off, if the tests run good enough.\n"
        #     f"The fix will be verified by running the affected tests.\n"
        #     f"Give Planner a complete report on which tests now work better",
        # )

        agents = PraisonAIAgents(
            agents=[testing_Agent,coding_Agent,planning_Agent],
            process="hierarchical",
            manager_llm="gpt-4o-mini",
            memory=True,
            memory_config=config
        )

        agents.start()








        # Token usage
        token_total = extract_last_token_total_from_logs()

        # Call REST service instead for evaluation changes from agent
        print(f"Calling SWE-Bench REST service with repo: {repo_dir}")
        test_payload = {
            "instance_id": instance_id,
            "repoDir": f"/repos/repo_{index}",  # mount with docker
            "FAIL_TO_PASS": fail_tests,
            "PASS_TO_PASS": pass_tests
        }
        res = requests.post("http://localhost:8082/test", json=test_payload)
        res.raise_for_status()
        result_raw = res.json().get("harnessOutput", "{}")
        result_json = json.loads(result_raw)
        if not result_json:
            raise ValueError("No data in harnessOutput – possible evaluation error or empty result")
        instance_id = next(iter(result_json))
        tests_status = result_json[instance_id]["tests_status"]
        fail_pass_results = tests_status["FAIL_TO_PASS"]
        fail_pass_total = len(fail_pass_results["success"]) + len(fail_pass_results["failure"])
        fail_pass_passed = len(fail_pass_results["success"])
        pass_pass_results = tests_status["PASS_TO_PASS"]
        pass_pass_total = len(pass_pass_results["success"]) + len(pass_pass_results["failure"])
        pass_pass_passed = len(pass_pass_results["success"])

        # Log results
        os.chdir(start_dir)
        with open(LOG_FILE, "a", encoding="utf-8") as log:
            log.write(f"\n--- TESTCASE {index} ---\n")
            log.write(f"FAIL_TO_PASS passed: {fail_pass_passed}/{fail_pass_total}\n")
            log.write(f"PASS_TO_PASS passed: {pass_pass_passed}/{pass_pass_total}\n")
            log.write(f"Total Tokens Used: {token_total}\n")
        print(f"Test case {index} completed and logged.")

    except Exception as e:
        os.chdir(start_dir)
        with open(LOG_FILE, "a", encoding="utf-8") as log:
            log.write(f"\n--- TESTCASE {index} ---\n")
            log.write(f"Error: {e}\n")
        print(f"Error in test case {index}: {e}")


def extract_last_token_total_from_logs():
    log_dir = r"logs"
    log_files = [f for f in os.listdir(log_dir) if f.endswith(".log")]
    if not log_files:
        return "No logs found"

    log_files.sort(reverse=True)

    latest_log_path = os.path.join(log_dir, log_files[0])
    with open(latest_log_path, 'r', encoding='utf-8') as f:
        lines = f.readlines()

    for line in reversed(lines):
        match = re.search(r'Cumulative Total=(\d+)', line)
        if match:
            return int(match.group(1))

    return "Cumulative Total not found"


async def main():
    for i in range(2, 3):
        await handle_task(i)


if __name__ == "__main__":
    asyncio.run(main())
