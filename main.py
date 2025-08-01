from dotenv import load_dotenv
load_dotenv()
import asyncio
import json
import re
import requests
import subprocess
import fnmatch
import os
from praisonaiagents import Agent, Task, PraisonAIAgents
from praisonaiagents.tools import read_file, write_file, list_files, get_file_info, copy_file, move_file, delete_file, calculator_tools
from praisonaiagents.tools import (
    evaluate, solve_equation, convert_units,
    calculate_statistics, calculate_financial
)
from praisonaiagents.tools import (
    execute_code, analyze_code, format_code,
    lint_code, disassemble_code
)
from pydantic import BaseModel
from typing import Optional

class DataForCoder(BaseModel):
    task_for_file: str
    path: Optional[str] = "normal"


API_URL = "http://localhost:8081/task/index/"  # API endpoint for SWE-Bench-Lite
LOG_FILE = "results.log"


def find_files_recursively(path_from_root: str, pattern: str) -> str:
    root_dir = os.getcwd()
    directory = os.path.join(root_dir,path_from_root)

    return_files = ""
    for root, dirs, files in os.walk(directory):
        for basename in files:
            if fnmatch.fnmatch(basename, pattern):
                filename = os.path.join(root, basename)
                return_files += filename + "\n"

    if(return_files.count("\n") > 70):
        return "There were over 70 files found with that pattern, please use a more precise pattern"
    return return_files

def replace_in_file(path_from_root : str, old_string : str, new_string : str) -> str:
    root_dir = os.getcwd()
    filename = os.path.join(root_dir, path_from_root)

    try:
        with open(filename) as f:
            s = f.read()
            if old_string not in s:
                return f"{old_string} not found in {filename}"


        with open(filename, 'w') as f:
            s = s.replace(old_string, new_string)
            f.write(s)
            return "String successfully replaced"

    except Exception:
        return "There was an error trying to replace content in the file, probably the file was not found."

async def handle_task(index):
    print(os.getenv("OPEN_API_KEY"))


    api_url = f"{API_URL}{index}"
    print(f"Fetching test case {index} from {api_url}...")
    root_dir = os.path.dirname(os.path.abspath(__file__))
    repo_dir = os.path.join(root_dir+ r"\repos", f"repo_{index}")  # Use unique repo directory per task
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
                  "You have a highly capable Coder at your disposal.\n"
                  "Always tell them the corresponding file paths to their tasks.",
            verbose=True,

            tools=[read_file, list_files, find_files_recursively],
            allow_delegation=True,
            self_reflect=True,
            min_reflect=1,
            max_reflect=3,
            instructions=f"Do this task with your teammate with the following roles:\n"
            f"Always research into the given repository and find out what the problem is, before concluding.\n"
            f"- Coder: makes actual changes to the code files in the Git repository\n"
            f"Work in the directory: repos/repo_{index}. This is a Git repository.\n"
            f"Your goal is to fix the problem described below.\n"
            f"All code changes must be saved to the files, so they appear in `git diff`.\n"
            f"Problem description:\n\n"
            f"{prompt}\n\n"
            f"Make sure the fix is minimal and only touches what's necessary to resolve the failing tests.\n"
            f"Give the coder agent instructions, after you have developed a plan. ALWAYS give them all relevant paths for their tasks."
        )

        coding_Agent = Agent(
            name="Coder",
            backstory="You are a senior software developer, having specialized in fixing special problems in repositiories.",
            goal="Resolve the coding tasks given to you by the Planner.\n"
                 "Write the fixes directly into the files, that you are supposed to repair.\n"
                 "Make sure the fix is minimal and only touches what's necessary to resolve the failing tests",
            verbose=True,
            self_reflect=True,
            min_reflect=1,
            max_reflect=3,
            code_execution_mode = "unsafe", #A little risk to spice things up
            tools=[read_file, replace_in_file,find_files_recursively],
            allow_code_execution=True,
            instructions=f"Follow the given coding instructions by Planner\n"
                        f"fWork in the directory: repos/repo_{index}. This is a Git repository.\n"
                        f"Your goal is to fix the problem described below.\n"
                        f"All code changes must be saved to the files, so they appear in `git diff`.\n"
                        f"The fix will be verified by running the affected tests.\n"
                        f"Make sure the fix is minimal and only touches what's necessary to resolve the failing tests. Tell the planner when you think you're done coding."
                        f"To write code, use the replace_in_file tool, make sure to make the string you want to be replaced specific enough so only the right string gets replaced."
                        f"Also see that when you give the old string more context, that the new string needs the same context added too. Also some code might be in python so take care of the correct indentation!",
        )


        print(f"Launching agents (PraisonAI)...")


        task = Task(
            name="Fixing_issue_in_repo_task",
            description=f"Do this task with your team of two other agents with the following roles:\n"
            f"Always research into the given repository and find out what the problem is, before concluding.\n"
            f"- Coder: makes actual changes to the code files in the Git repository\n"
            f"- Tester: runs the test suite and checks whether the bug is resolved\n\n"
            f"Work in the directory: repos/repo_{index}. This is a Git repository.\n"
            f"Your goal is to fix the problem described below.\n"
            f"All code changes must be saved to the files, so they appear in `git diff`.\n"
            f"The fix will be verified by running the affected tests.\n"
            f"Problem description:\n\n"
            f"{prompt}\n\n"
            f"Make sure the fix is minimal and only touches what's necessary to resolve the failing tests.\n"
            f"Your job done after you made a plan for coder or tester, you can also end your task if you know no way forward",
            agent=planning_Agent,
            next_tasks=["coding_task","testing_task"],

        )

        coding_task = Task(
            name="coding_task",
            description=f"Follow the given coding instructions by Planner\n"
                        f"fWork in the directory: repos/repo_{index}. This is a Git repository.\n"
            f"Your goal is to fix the problem described below.\n"
            f"All code changes must be saved to the files, so they appear in `git diff`.\n"
            f"The fix will be verified by running the affected tests.\n"
            f"Make sure the fix is minimal and only touches what's necessary to resolve the failing tests."
            f"If you have made your changes you can end your task, you can also end the task if you know no way forward",
            agent=coding_Agent,
            #next_tasks=["further_planning_task"],

        )


        agents = PraisonAIAgents(
            agents=[planning_Agent,coding_Agent],
            tasks=[task,coding_task],
            process="workflow",
            manager_llm="gpt-4o-mini",
            max_iter=2,

        )

        agents.start()




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
    for i in range(1,2):
        await handle_task(i)


if __name__ == "__main__":
    asyncio.run(main())
