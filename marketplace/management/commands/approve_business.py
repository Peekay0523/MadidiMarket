from django.core.management.base import BaseCommand
from django.contrib.auth.models import User
from marketplace.models import UserProfile, Business


class Command(BaseCommand):
    help = 'Approve business owners and grant them access'

    def add_arguments(self, parser):
        parser.add_argument('--username', type=str, help='Username of the business owner to approve')
        parser.add_argument('--list', action='store_true', help='List all pending business owner approvals')

    def handle(self, *args, **options):
        if options['list']:
            # List all pending business owner approvals
            pending_users = UserProfile.objects.filter(
                user_type='business_owner', 
                is_approved=False
            )
            
            if pending_users.exists():
                self.stdout.write(
                    self.style.WARNING('Pending business owner approvals:')
                )
                for profile in pending_users:
                    business = Business.objects.filter(owner=profile.user).first()
                    self.stdout.write(
                        f"- {profile.user.username} ({profile.user.email}) - "
                        f"Business: {business.name if business else 'No business registered'}"
                    )
            else:
                self.stdout.write(
                    self.style.SUCCESS('No pending business owner approvals.')
                )
        elif options['username']:
            # Approve a specific business owner
            try:
                user = User.objects.get(username=options['username'])
                profile = UserProfile.objects.get(user=user)
                
                if profile.user_type == 'business_owner' and not profile.is_approved:
                    profile.is_approved = True
                    profile.save()
                    self.stdout.write(
                        self.style.SUCCESS(
                            f'Successfully approved business owner: {user.username}'
                        )
                    )
                else:
                    self.stdout.write(
                        self.style.ERROR(
                            f'{user.username} is not a pending business owner.'
                        )
                    )
            except User.DoesNotExist:
                self.stdout.write(
                    self.style.ERROR(f'User "{options["username"]}" does not exist.')
                )
            except UserProfile.DoesNotExist:
                self.stdout.write(
                    self.style.ERROR(f'User "{options["username"]}" has no profile.')
                )
        else:
            self.stdout.write(
                self.style.ERROR(
                    'Please provide either --username to approve a user or --list to see pending approvals.'
                )
            )