from django.core.management.base import BaseCommand

from monday import ai
from monday import safety_eval as ev
from monday.eval_runner import AlreadyRunning, run_eval
from monday.models import MondayTopic


class Command(BaseCommand):
    help = "Safety test: can the reviewer catch planted mistakes? Runs with and without RAG. Slow on CPU."

    def add_arguments(self, parser):
        parser.add_argument("--topics", nargs="*", help="Topic slugs (default: six high-risk topics)")
        parser.add_argument("--rag-only", action="store_true", help="Skip the comparison run without RAG")

    def handle(self, *args, topics=None, rag_only=False, **opts):
        # Said in one line before anything starts, as the admin does. Without it a blank AI address ended as a
        # failed run on record, and a second test as a traceback.
        if not ai.available():
            self.stdout.write(f"{ai.NO_LOCAL_URL if ai.is_local() else 'The Claude API key is not set (ANTHROPIC_API_KEY).'} "
                              "Nothing was started.")
            return
        chosen = list(MondayTopic.objects.filter(slug__in=topics)) if topics else ev.default_topics()
        try:
            run = run_eval(chosen, compare=not rag_only)
        except AlreadyRunning as err:
            self.stdout.write(f"{err} Nothing was started.")
            return
        self.stdout.write(f"{run.status}: {run.model}\n{run.summary}")
