"""Sequential fixture writes for tests not exercising stale editor behavior."""
import manager_corrections as C


def revision(path, key, version):
    # Historical fixtures can contain retired themes: revision lookup must not
    # validate their tags against today's vocabulary.
    db = C._connect(path)
    try:
        row = db.execute(
            "SELECT saved_at FROM corrections WHERE review_key=? AND rules_version=?",
            (key, version)).fetchone()
        return row[0] if row else None
    finally:
        db.close()


def save_fixture(path, key, positive, negative, version):
    C.save_correction(path, key, positive, negative, version,
                      expected_revision=revision(path, key, version))


def undo_fixture(path, key, version):
    C.undo_correction(path, key, version,
                      expected_revision=revision(path, key, version))
