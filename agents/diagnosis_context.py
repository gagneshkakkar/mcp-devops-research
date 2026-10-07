from dataclasses import dataclass, asdict
from typing import List, Dict


@dataclass
class DiagnosisContext:
    """
    Structured evidence collected from a failed CI run.
    """

    run_id: int

    build_status: str

    failed_tests: List[str]

    errors: List[str]

    assertions: List[Dict[str, str]]

    test_source: str

    implementation_files: List[str]

    implementation_source: Dict[str, str]

    def to_dict(self):
        """
        Convert the diagnosis context into a dictionary.
        """

        return asdict(self)