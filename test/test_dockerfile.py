from pathlib import Path


def test_dockerfile_uses_a_non_root_user():
    dockerfile = Path(__file__).parents[1] / "Dockerfile"
    users = [
        line.split(maxsplit=1)[1]
        for line in dockerfile.read_text().splitlines()
        if line.strip().upper().startswith("USER ")
    ]

    assert users
    user_id = users[-1].split(":", maxsplit=1)[0]
    assert user_id.isdigit()
    assert int(user_id) != 0
