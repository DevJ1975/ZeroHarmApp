from django.core.management.base import BaseCommand

from monday import safety_eval as ev
from monday.eval_runner import run_eval
from monday.models import MondayTopic


class Command(BaseCommand):
    help = "Safety test: can the reviewer catch planted mistakes? Runs with and without RAG. Slow on CPU."

    def add_arguments(self, parser):
        parser.add_argument("--topics", nargs="*", help="Topic slugs (default: six high-risk topics)")
        parser.add_argument("--rag-only", action="store_true", help="Skip the comparison run without RAG")

    def handle(self, *args, topics=None, rag_only=False, **opts):
        chosen = list(MondayTopic.objects.filter(slug__in=topics)) if topics else ev.default_topics()
        run = run_eval(chosen, compare=not rag_only)
        self.stdout.write(f"{run.status}: {run.model}\n{run.summary}")
