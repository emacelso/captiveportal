from django.shortcuts import render, get_object_or_404, redirect
from django.http import HttpResponse, Http404, HttpResponseRedirect
from django.urls import reverse, reverse_lazy
from django.views import generic
import datetime
from django.utils import timezone
from urllib.parse import urlencode
from .models import Portal, Roll, Voucher
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import PermissionDenied
from django.contrib import messages



def redirect_params(url, params=None):
    response = redirect(url)
    if params:
        query_string = urlencode(params, True)
        response['Location'] += '?' + query_string
    return response


class PortalListView(LoginRequiredMixin, generic.ListView):
    model = Portal

    def get_queryset(self):
        # Limit only to active portals
        qs = super().get_queryset()
        qs = qs.filter(active=True)

        # Hide portals where the user has no groups that are allowed printing.
        groups = self.request.user.groups.values_list('id', flat=True)
        qs = qs.filter(allow_printing__in=groups)

        # Groups query can cause duplicate records.
        qs = qs.distinct()

        return qs


@login_required
def printselection(request, portal_id):
    
    # Make sure the portal is active and user has access.
    groups = request.user.groups.values_list('id', flat=True)
    try:
        portal = Portal.objects.filter(pk=portal_id,active=True,allow_printing__in=groups).distinct().get()
    except Portal.DoesNotExist:
        raise Http404("Portal does not exist")


    if request.method == 'POST':
        printer_type = request.POST['printer_type']
        quantity = int(request.POST['quantity'])
        roll_id = int(request.POST['roll_id'])

        roll = get_object_or_404(Roll, pk=roll_id)

        # Validate parameters
        if printer_type not in ('address_labels', 'letter'):
            messages.add_message(request, messages.ERROR, 'Invalid printer type')
            return render(request, 'voucher/print_selection.html', {'portal':portal, 'printer_type':printer_type, 'quantity':quantity, 'roll_id': roll_id})
        if (quantity < 1):
            messages.add_message(request, messages.ERROR, 'Invalid quantity.')
            return render(request, 'voucher/print_selection.html', {'portal':portal, 'printer_type':printer_type, 'quantity':quantity, 'roll_id': roll_id})
        if (quantity > roll.remaining_vouchers()):
            messages.add_message(request, messages.ERROR, 'Not enough vouchers available.')
            return render(request, 'voucher/print_selection.html', {'portal':portal, 'printer_type':printer_type, 'quantity':quantity, 'roll_id': roll_id})
            
        # Get only unprinted vouchers from this roll
        vouchers = Voucher.objects.filter(roll=roll.id)
        vouchers = vouchers.filter(date_printed__isnull=True)
        # Retrieve the id values as a flat list (convert to list(), otherwise the query will change when we update these values!)
        vouchers = list(vouchers.values_list('id', flat=True)[:quantity])

        # Mark these vouchers as printed
        Voucher.objects.filter(id__in=vouchers).update(date_printed=timezone.now(),printed_by=request.user.get_username())

        return redirect_params(reverse('voucher:print', kwargs={'portal_id': portal_id, 'roll_id': roll_id, 'printer_type': printer_type}), {'v': vouchers})
    else:
        return render(request, 'voucher/print_selection.html', {'portal':portal,'quantity':5})

@login_required
def print(request, portal_id, roll_id, printer_type):
    # Make sure the portal is active and user has access.
    groups = request.user.groups.values_list('id', flat=True)
    try:
        portal = Portal.objects.filter(pk=portal_id,active=True,allow_printing__in=groups).distinct().get()
    except Portal.DoesNotExist:
        raise Http404("Portal does not exist")

    roll = get_object_or_404(Roll, pk=roll_id)
    
    # Retrieve the vouchers by id, and verify they are ok to print (someone could have altered GET string)
    # Make sure they match the roll, and were marked as printed within the last hour
    voucherlist = request.GET.getlist('v')
    vouchers = Voucher.objects.filter(id__in=voucherlist)
    vouchers = vouchers.filter(roll=roll.id)
    vouchers = vouchers.filter(date_printed__isnull=False)
    last_hour = timezone.now() - datetime.timedelta(hours=1)
    vouchers = vouchers.filter(date_printed__gt=last_hour)
    codes = list(vouchers.values_list('code', flat=True))
    
    context = {
        'roll': roll,
        'portal': portal,
        'printer_type': printer_type,
        'codes': codes,
    }

    if printer_type == 'address_labels':
        return render(request, 'voucher/print_dymo.html', context)
    elif printer_type == 'letter':
        return render(request, 'voucher/print_letter.html', context)
    else:
        return render(request, 'voucher/print_letter.html', context)